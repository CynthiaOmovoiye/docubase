"""
Background ingestion jobs (ARQ).

These run outside the request cycle and are triggered when:
- A new source is attached to a twin (first full sync)
- A webhook event fires (push to repo, file change in Drive)
- A user manually triggers re-sync

Job flow:
  1. Load Source from DB, including ConnectedAccount if present
  2. Load TwinConfig for allow_code_snippets policy
  3. Mark source as 'ingesting'
  4. Resolve OAuth access token (decrypt + refresh if needed)
  5. Instantiate the correct connector
  6. Validate connection
  7. Fetch raw content (delta or full, depending on last_commit_sha / last_page_token)
  8. For full syncs: clear all existing chunks
     For delta syncs: pipeline handles path-level chunk deletion
  9. Run knowledge pipeline (policy + extraction + embedding + DB write)
 10. Update sync cursors (last_commit_sha, last_page_token) on the Source row
 11. Register a webhook with the provider if not already registered (first sync)
 12. Mark source as 'processing' (fully indexed, awaiting memory rebuild)
 13. Enqueue memory extraction job; only mark the source 'ready' after it succeeds

All jobs are idempotent: if re-run, a full sync clears existing chunks;
a delta sync prunes only the changed paths.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime
from time import perf_counter
from sqlalchemy import update

from arq.connections import RedisSettings
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.db import get_async_session
from app.core.logging import get_logger
from app.domains.embedding.embedder import (
    EmbeddingProfile,
    get_fallback_embedding_profile,
    get_primary_embedding_profile,
    resolve_embedding_profile,
)
from app.domains.integrations.service import resolve_access_token
from app.domains.knowledge.evidence import (
    build_root_hash,
    hash_text,
    resolve_snapshot_id,
    stale_after_hours_for_source,
)
from app.domains.knowledge.git_index import (
    build_git_index_health,
    replace_git_activity_for_source,
)
from app.domains.knowledge.implementation_facts import clear_implementation_facts_for_source
from app.domains.knowledge.implementation_index import clear_implementation_index_for_source
from app.domains.knowledge.pipeline import (
    clear_chunks_for_source,
    process_connector_result,
)
from app.domains.memory.queue_state import (
    PENDING_TTL_SECONDS,
    clear_memory_brief_arq_job,
    memory_brief_job_id,
    memory_brief_pending_key,
)
from app.domains.sources.service import (
    mark_source_failed,
    mark_source_ingesting,
    mark_source_processing,
    mark_processing_sources_failed,
    mark_processing_sources_ready,
)
from app.models.chunk import Chunk
from app.models.implementation_index import IndexedFile, IndexedRelationship, IndexedSymbol
from app.models.source import Source, SourceStatus, SourceType
from app.models.twin import TwinConfig

logger = get_logger(__name__)
settings = get_settings()


async def ingest_source(ctx: dict, source_id: str) -> dict:
    """Main ingestion job. ctx is the ARQ worker context dict."""
    logger.info("ingestion_job_start", source_id=source_id)
    job_started_at = perf_counter()

    async with get_async_session() as db:
        try:
            # ── 1. Load source with twin and connected_account ────────────────
            source_result = await db.execute(
                select(Source)
                .options(
                    selectinload(Source.twin),
                    selectinload(Source.connected_account),
                )
                .where(Source.id == uuid.UUID(source_id))
            )
            source = source_result.scalar_one_or_none()

            if source is None:
                logger.error("ingestion_source_not_found", source_id=source_id)
                return {"source_id": source_id, "status": "not_found"}

            twin_id = str(source.twin_id)

            # ── 2. Load TwinConfig ────────────────────────────────────────────
            config_result = await db.execute(
                select(TwinConfig).where(TwinConfig.twin_id == source.twin_id)
            )
            twin_config = config_result.scalar_one_or_none()
            allow_code_snippets = twin_config.allow_code_snippets if twin_config else False

            # ── 3. Mark as ingesting ──────────────────────────────────────────
            await mark_source_ingesting(source_id, db)
            await db.commit()

            # ── 4. Resolve OAuth access token ─────────────────────────────────
            access_token: str | None = None
            if source.connected_account_id is not None:
                try:
                    access_token = await resolve_access_token(
                        str(source.connected_account_id), db
                    )
                except Exception as exc:
                    msg = f"Failed to resolve OAuth token: {exc}"
                    logger.error("ingestion_token_resolve_failed", source_id=source_id, error=str(exc))
                    await mark_source_failed(source_id, msg, db)
                    await db.commit()
                    return {"source_id": source_id, "status": "failed", "error": msg}

            # ── 5. Instantiate connector ──────────────────────────────────────
            connector = _get_connector(source.source_type)
            if connector is None:
                msg = f"No connector implemented for source_type: {source.source_type.value}"
                logger.error("ingestion_no_connector", source_id=source_id, source_type=source.source_type.value)
                await mark_source_failed(source_id, msg, db)
                await db.commit()
                return {"source_id": source_id, "status": "failed", "error": msg}

            # ── 6. Validate connection ────────────────────────────────────────
            try:
                valid = await connector.validate_connection(
                    source.connection_config, access_token=access_token
                )
                if not valid:
                    raise ValueError("Connection validation returned False")
            except Exception as exc:
                msg = f"Connection validation failed: {exc}"
                logger.error("ingestion_validation_failed", source_id=source_id, error=str(exc))
                await mark_source_failed(source_id, msg, db)
                await db.commit()
                return {"source_id": source_id, "status": "failed", "error": msg}

            # ── 7. Fetch content (delta or full) ──────────────────────────────
            connection_config = dict(source.connection_config)
            connection_config["source_id"] = source_id

            try:
                connector_result = await connector.fetch(
                    connection_config,
                    access_token=access_token,
                    last_commit_sha=source.last_commit_sha,
                    last_page_token=source.last_page_token,
                )
                connector_result.source_id = source_id
            except Exception as exc:
                msg = f"Content fetch failed: {exc}"
                logger.error("ingestion_fetch_failed", source_id=source_id, error=str(exc))
                await mark_source_failed(source_id, msg, db)
                await db.commit()
                return {"source_id": source_id, "status": "failed", "error": msg}

            # ── 8. Clear stale chunks (full sync only) ────────────────────────
            incoming_root_hash = _incoming_root_hash(connector_result)
            if _should_short_circuit_full_sync(
                source=source,
                connector_result=connector_result,
                incoming_root_hash=incoming_root_hash,
                allow_code_snippets=allow_code_snippets,
            ):
                await _finalise_noop_full_sync(
                    source=source,
                    connector_result=connector_result,
                    incoming_root_hash=incoming_root_hash,
                    db=db,
                )
                await db.commit()
                logger.info(
                    "ingestion_noop_short_circuit",
                    source_id=source_id,
                    snapshot_id=source.snapshot_id,
                    snapshot_root_hash=source.snapshot_root_hash,
                    duration_ms=round((perf_counter() - job_started_at) * 1000, 2),
                )
                return {
                    "source_id": source_id,
                    "status": "ready",
                    "files_received": len(connector_result.files),
                    "files_processed": 0,
                    "chunks_created": 0,
                    "chunks_embedded": 0,
                    "snapshot_id": source.snapshot_id,
                    "snapshot_root_hash": source.snapshot_root_hash,
                    "noop": True,
                }

            if connector_result.is_full_sync:
                deleted_count = await clear_chunks_for_source(source_id, db)
                implementation_deleted = await clear_implementation_index_for_source(source_id, db)
                facts_deleted = await clear_implementation_facts_for_source(source_id, db)
                if deleted_count > 0 or implementation_deleted > 0 or facts_deleted > 0:
                    logger.info(
                        "ingestion_stale_chunks_cleared",
                        source_id=source_id,
                        deleted=deleted_count,
                        implementation_deleted=implementation_deleted,
                        implementation_facts_deleted=facts_deleted,
                    )

            # ── 9. Run knowledge pipeline ─────────────────────────────────────
            try:
                stats = await process_connector_result(
                    result=connector_result,
                    twin_id=twin_id,
                    allow_code_snippets=allow_code_snippets,
                    db=db,
                    embedding_profiles=_profiles_for_source_sync(source, connector_result.is_full_sync),
                )
            except Exception as exc:
                msg = f"Knowledge pipeline failed: {exc}"
                logger.error("ingestion_pipeline_error", source_id=source_id, error=str(exc))
                await db.rollback()
                async with get_async_session() as recovery_db:
                    await mark_source_failed(source_id, msg, recovery_db)
                    await recovery_db.commit()
                return {"source_id": source_id, "status": "failed", "error": msg}

            if stats.get("embedding_provider"):
                source.embedding_provider = stats["embedding_provider"]
                source.embedding_model = stats["embedding_model"]
                source.embedding_dimensions = stats["embedding_dimensions"]

            # ── 10. Update sync cursors ───────────────────────────────────────
            if connector_result.head_sha:
                source.last_commit_sha = connector_result.head_sha
                logger.info(
                    "ingestion_cursor_updated",
                    source_id=source_id,
                    head_sha=connector_result.head_sha[:7],
                )
            if connector_result.next_page_token:
                source.last_page_token = connector_result.next_page_token

            # ── 11. Register webhook (first sync only) ────────────────────────
            if source.webhook_id is None and connector_result.is_full_sync:
                await _register_webhook(source, access_token)

            # ── 12. Mark processing + hide stale memory until refresh completes ──
            await _set_memory_brief_status(twin_id, "generating", db)
            await mark_source_processing(source_id, db)
            await db.commit()

            logger.info(
                "ingestion_job_complete",
                source_id=source_id,
                duration_ms=round((perf_counter() - job_started_at) * 1000, 2),
                **stats,
            )

            # ── 13. Enqueue memory extraction (required before source is ready) ──
            try:
                await _enqueue_memory_extraction(twin_id)
                logger.info("memory_extraction_enqueued", twin_id=twin_id, source_id=source_id)
            except Exception as exc:
                msg = f"Memory brief enqueue failed: {exc}"
                logger.error(
                    "memory_extraction_enqueue_failed",
                    twin_id=twin_id,
                    source_id=source_id,
                    error=str(exc),
                )
                await mark_source_failed(source_id, msg, db)
                await _set_memory_brief_status(twin_id, "failed", db)
                await db.commit()
                return {"source_id": source_id, "status": "failed", "error": msg}

            return {"source_id": source_id, "status": "processing", **stats}

        except Exception as exc:
            logger.error(
                "ingestion_job_unexpected_error",
                source_id=source_id,
                error=str(exc),
                exc_info=True,
            )
            try:
                await db.rollback()
                async with get_async_session() as recovery_db:
                    await mark_source_failed(source_id, f"Unexpected error: {exc}", recovery_db)
                    await recovery_db.commit()
            except Exception:
                pass
            return {"source_id": source_id, "status": "failed", "error": str(exc)}


# ─── Webhook registration ─────────────────────────────────────────────────────


async def _register_webhook(source: Source, access_token: str | None) -> None:
    """
    Register a webhook with the provider for push-based sync.

    Stores webhook_id and a per-source webhook_secret on the Source row.
    The secret is used later in the /webhooks route for HMAC verification.

    Errors are logged but not fatal — webhook registration must not block the
    source from reaching its later processing/ready states.
    Webhooks are a best-effort optimisation; polling fallback can be added later.
    """
    if not access_token:
        return

    import httpx

    webhook_secret = secrets.token_hex(32)
    webhook_url = f"{settings.app_base_url}/api/v1/webhooks/{source.source_type.value}"

    # GitHub/GitLab cannot reach localhost — skip registration in local dev to
    # avoid noisy 422 errors. Webhooks are a best-effort optimisation anyway.
    if any(h in settings.app_base_url for h in ("localhost", "127.0.0.1", "0.0.0.0")):
        logger.debug(
            "webhook_registration_skipped_local",
            source_id=str(source.id),
            app_base_url=settings.app_base_url,
        )
        return

    try:
        if source.source_type == SourceType.github_repo:
            repo = source.connection_config.get("repo_url", "")
            async with httpx.AsyncClient(
                base_url="https://api.github.com",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=15.0,
            ) as client:
                resp = await client.post(
                    f"/repos/{repo}/hooks",
                    json={
                        "name": "web",
                        "active": True,
                        "events": ["push"],
                        "config": {
                            "url": webhook_url,
                            "content_type": "json",
                            "secret": webhook_secret,
                            "insecure_ssl": "0",
                        },
                    },
                )
                resp.raise_for_status()
                source.webhook_id = str(resp.json().get("id", ""))
                source.webhook_secret = webhook_secret
                logger.info("webhook_registered", source_id=str(source.id), provider="github")

        elif source.source_type == SourceType.gitlab_repo:
            project = source.connection_config.get("repo_url", "")
            from urllib.parse import quote
            from app.core.config import get_settings as _gs
            gl_base = _gs().gitlab_base_url.rstrip("/")
            async with httpx.AsyncClient(
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=15.0,
            ) as client:
                resp = await client.post(
                    f"{gl_base}/api/v4/projects/{quote(project, safe='')}/hooks",
                    json={
                        "url": webhook_url,
                        "push_events": True,
                        "token": webhook_secret,
                    },
                )
                resp.raise_for_status()
                source.webhook_id = str(resp.json().get("id", ""))
                source.webhook_secret = webhook_secret
                logger.info("webhook_registered", source_id=str(source.id), provider="gitlab")

    except Exception as exc:
        logger.warning(
            "webhook_registration_failed",
            source_id=str(source.id),
            source_type=source.source_type.value,
            error=str(exc),
        )


# ─── Connector registry ───────────────────────────────────────────────────────


def _get_connector(source_type: SourceType):
    """
    Return the connector instance for a given source type.
    Returns None for unimplemented connectors — callers log and fail gracefully.
    """
    from app.connectors.registry import get_connector as _registry_get
    try:
        return _registry_get(source_type)
    except NotImplementedError:
        logger.warning("ingestion_connector_not_implemented", source_type=source_type.value)
        return None


def _profiles_for_source_sync(
    source: Source,
    is_full_sync: bool,
) -> list[EmbeddingProfile]:
    """
    Return the ordered embedding profiles allowed for this sync pass.

    Full syncs may switch providers because all source chunks are being rebuilt.
    Delta syncs keep the existing source profile sticky so we never mix vector
    spaces inside a partially updated source.
    """
    if (
        not is_full_sync
        and source.embedding_provider
        and source.embedding_model
        and source.embedding_dimensions
    ):
        return [
            resolve_embedding_profile(
                source.embedding_provider,
                source.embedding_model,
                source.embedding_dimensions,
                use_default_model=True,
            )
        ]

    profiles = [get_primary_embedding_profile()]
    fallback = get_fallback_embedding_profile()
    if fallback is not None:
        profiles.append(fallback)
    return profiles


def _incoming_root_hash(connector_result) -> str | None:
    fingerprints = [
        (raw_file.path, hash_text(raw_file.content.replace("\x00", "")))
        for raw_file in connector_result.files
        if raw_file.path
    ]
    return build_root_hash(fingerprints)


def _should_short_circuit_full_sync(
    *,
    source: Source,
    connector_result,
    incoming_root_hash: str | None,
    allow_code_snippets: bool,
) -> bool:
    if not connector_result.is_full_sync:
        return False
    if source.index_mode.value != "strict":
        return False
    implementation_index = (source.index_health or {}).get("implementation_index") or {}
    if implementation_index.get("schema_version", 0) < 2:
        return False
    if implementation_index.get("fact_schema_version", 0) < 4:
        return False
    if implementation_index.get("ready") is not True:
        return False
    if not incoming_root_hash or incoming_root_hash != source.snapshot_root_hash:
        return False
    mirror = (source.index_health or {}).get("canonical_mirror") or {}
    if mirror.get("ready") is not True:
        return False
    if mirror.get("snapshot_root_hash") and mirror.get("snapshot_root_hash") != source.snapshot_root_hash:
        return False
    if mirror.get("snapshot_id") and mirror.get("snapshot_id") != getattr(source, "snapshot_id", None):
        return False
    expected_files = int(((source.structure_index or {}).get("total_files") if getattr(source, "structure_index", None) else 0) or 0)
    mirrored_files = int(mirror.get("file_count") or 0)
    if expected_files > 0 and mirrored_files <= 0:
        return False
    policy = (source.index_health or {}).get("policy") or {}
    if policy.get("allow_code_snippets") != allow_code_snippets:
        return False
    return True


async def _finalise_noop_full_sync(
    *,
    source: Source,
    connector_result,
    incoming_root_hash: str | None,
    db,
) -> None:
    snapshot_id = resolve_snapshot_id(
        connector_result.fetch_metadata,
        connector_result.head_sha,
        connector_result.next_page_token,
        incoming_root_hash,
    )

    if connector_result.head_sha:
        source.last_commit_sha = connector_result.head_sha
    if connector_result.next_page_token:
        source.last_page_token = connector_result.next_page_token
    if snapshot_id:
        source.snapshot_id = snapshot_id
    if incoming_root_hash:
        source.snapshot_root_hash = incoming_root_hash

    health = dict(source.index_health or {})
    health["snapshot_id"] = source.snapshot_id
    health["snapshot_root_hash"] = source.snapshot_root_hash
    coverage = dict(health.get("coverage") or {})
    coverage["files_received"] = len(connector_result.files)
    coverage["files_processed"] = 0
    coverage["chunks_created"] = 0
    coverage["chunks_embedded"] = 0
    health["coverage"] = coverage
    health["freshness"] = {
        "last_indexed_at": datetime.now(UTC).isoformat(),
        "stale_after_hours": stale_after_hours_for_source(source.source_type),
    }
    source.index_health = health
    source.status = SourceStatus.ready
    source.last_error = None

    await db.execute(
        update(Chunk)
        .where(Chunk.source_id == source.id)
        .values(snapshot_id=source.snapshot_id)
    )
    await db.execute(
        update(IndexedFile)
        .where(IndexedFile.source_id == source.id)
        .values(snapshot_id=source.snapshot_id)
    )
    await db.execute(
        update(IndexedSymbol)
        .where(IndexedSymbol.source_id == source.id)
        .values(snapshot_id=source.snapshot_id)
    )
    await db.execute(
        update(IndexedRelationship)
        .where(IndexedRelationship.source_id == source.id)
        .values(snapshot_id=source.snapshot_id)
    )
    await db.flush()


async def _set_memory_brief_status(
    twin_id: str,
    status: str,
    db,
) -> None:
    result = await db.execute(
        select(TwinConfig).where(TwinConfig.twin_id == uuid.UUID(twin_id))
    )
    config = result.scalar_one_or_none()
    if config is not None:
        config.memory_brief_status = status
        await db.flush()


async def _enqueue_memory_extraction(twin_id: str) -> None:
    from arq import create_pool

    redis_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        await clear_memory_brief_arq_job(redis_pool, twin_id)
        await redis_pool.enqueue_job(
            "generate_memory_brief",
            twin_id,
            _job_id=memory_brief_job_id(twin_id),
        )
        await redis_pool.setex(
            memory_brief_pending_key(twin_id),
            PENDING_TTL_SECONDS,
            "1",
        )
    finally:
        await redis_pool.aclose()


# ─── Memory extraction job ────────────────────────────────────────────────────


async def generate_memory_brief(ctx: dict, twin_id: str) -> dict:
    """
    Post-ingestion memory extraction job.

    Runs after ingest_source completes for any source belonging to this twin.
    Orchestrates the full memory extraction pipeline:
      1. Load twin — skip if not found or has no ready/processing sources
      2. Fetch commit history from git connectors (GitHub / GitLab)
      3. Run run_memory_extraction() — idempotent, redis-locked, never raises

    Returns a stats dict. Never raises.
    """
    logger.info("memory_extraction_job_start in ingestion.py", twin_id=twin_id)

    try:
        async with get_async_session() as db:
            try:
                # Load the twin's sources to find git connectors for commit history
                from sqlalchemy.orm import selectinload as _slo
                from app.models.source import Source, SourceType
                from app.domains.memory.service import run_memory_extraction
    
                sources_result = await db.execute(
                    select(Source)
                    .options(_slo(Source.connected_account))
                    .where(
                        Source.twin_id == uuid.UUID(twin_id),
                        Source.status.in_([SourceStatus.ready, SourceStatus.processing]),
                        Source.name != "__memory__",  # exclude phantom memory anchor source
                    )
                )
                sources = sources_result.scalars().all()
    
                if not sources:
                    logger.info(
                        "memory_extraction_no_ready_sources",
                        twin_id=twin_id,
                    )
                    return {"twin_id": twin_id, "status": "skipped", "reason": "no eligible sources"}
    
                # Fetch commits AND pull requests / merge requests from ALL git
                # sources attached to this twin and merge them.  This ensures that
                # when a twin has multiple repos (e.g. a stripped public mirror +
                # the full private repo) all commit history is captured.
                # Commits are deduplicated by SHA so the same commit isn't counted
                # twice if repos share history.
                all_commits: dict[str, dict] = {}   # sha → commit dict (dedup)
                all_prs: list[dict] = []
                git_source_types = {SourceType.github_repo, SourceType.gitlab_repo}
    
                logger.info(
                    "memory_extraction_sources_found",
                    twin_id=twin_id,
                    count=len(sources),
                    repos=[s.connection_config.get("repo_url", str(s.id)) for s in sources],
                )
    
                for source in sources:
                    if source.source_type not in git_source_types:
                        source.index_health = {
                            **dict(source.index_health or {}),
                            "git_index": build_git_index_health(
                                source_type=source.source_type,
                                snapshot_id=source.snapshot_id,
                            ),
                        }
                        continue
                    if source.connected_account_id is None:
                        source.index_health = {
                            **dict(source.index_health or {}),
                            "git_index": build_git_index_health(
                                source_type=source.source_type,
                                snapshot_id=source.snapshot_id,
                                ready=False,
                                error="No connected account available for git activity sync.",
                            ),
                        }
                        logger.info(
                            "memory_extraction_skip_no_oauth",
                            twin_id=twin_id,
                            source_id=str(source.id),
                            repo=source.connection_config.get("repo_url", ""),
                        )
                        continue
    
                    try:
                        commits: list[dict] = []
                        source_prs: list[dict] = []
                        access_token = await resolve_access_token(
                            str(source.connected_account_id), db
                        )
                        connector = _get_connector(source.source_type)
                        if connector is None:
                            continue
    
                        # Fetch commits — 90 days / 100 max keeps the GitHub API call
                        # under ~15 seconds for typical repos. 365 days / 200 commits
                        # was taking 60-70 seconds and causing the job to be killed by
                        # dev worker restarts. 90 days covers the "Recent Changes"
                        # section well enough; older history adds little for onboarding.
                        if hasattr(connector, "fetch_commit_history"):
                            commits = await connector.fetch_commit_history(
                                connection_config=source.connection_config,
                                access_token=access_token,
                                since_days=90,
                                max_commits=100,
                            )
                            new_commits = 0
                            for c in commits:
                                sha = c.get("sha", "")
                                if sha and sha not in all_commits:
                                    all_commits[sha] = c
                                    new_commits += 1
                        else:
                            new_commits = 0
    
                        # Fetch PRs / MRs (90 days, up to 50)
                        if hasattr(connector, "fetch_pr_history"):
                            source_prs = await connector.fetch_pr_history(
                                connection_config=source.connection_config,
                                access_token=access_token,
                                since_days=90,
                                max_prs=50,
                            )
                            all_prs.extend(source_prs)

                        await replace_git_activity_for_source(
                            source=source,
                            commits=commits,
                            pull_requests=source_prs,
                            db=db,
                        )

                        logger.info(
                            "memory_extraction_activity_loaded",
                            twin_id=twin_id,
                            source_id=str(source.id),
                            commits=new_commits,
                            prs=len(source_prs),
                        )
                    except Exception as exc:
                        source.index_health = {
                            **dict(source.index_health or {}),
                            "git_index": build_git_index_health(
                                source_type=source.source_type,
                                snapshot_id=source.snapshot_id,
                                ready=False,
                                error=str(exc),
                            ),
                        }
                        logger.warning(
                            "memory_extraction_activity_failed",
                            twin_id=twin_id,
                            source_id=str(source.id),
                            error=str(exc),
                        )
                        # Non-fatal — move on to the next source
    
                activity_history: list[dict] = list(all_commits.values()) + all_prs
                await db.commit()

                stats = await run_memory_extraction(
                    twin_id=twin_id,
                    db=db,
                    commit_history=activity_history or None,
                )
                if stats is None:
                    stats = {
                        "twin_id": twin_id,
                        "status": "failed",
                        "arch_chunks": 0,
                        "risk_chunks": 0,
                        "change_chunks": 0,
                        "brief_generated": False,
                        "error": "run_memory_extraction returned no stats",
                    }
                finalised_sources = 0
                if stats.get("status") == "ready":
                    finalised_sources = await mark_processing_sources_ready(twin_id, db)
                elif stats.get("status") == "failed":
                    finalised_sources = await mark_processing_sources_failed(
                        twin_id,
                        stats.get("error") or "Memory brief generation failed.",
                        db,
                    )
                if finalised_sources:
                    await db.commit()
                    stats["processing_sources_finalised"] = finalised_sources
                logger.info("stats in generate_memory_brief in ingestion.py", stats=stats)
                # Exclude twin_id from stats before unpacking — stats dict already
                # includes twin_id from run_memory_extraction(), and passing it as
                # both a keyword arg and via **stats causes TypeError.
                stats_log = {k: v for k, v in stats.items() if k != "twin_id"}
                logger.info("memory_extraction_job_complete", twin_id=twin_id, **stats_log)
                return stats
    
            except Exception as exc:
                logger.error(
                    "memory_extraction_job_unexpected_error",
                    twin_id=twin_id,
                    error=str(exc),
                    exc_info=True,
                )
                return {"twin_id": twin_id, "status": "failed", "error": str(exc)}
    finally:
        try:
            from app.core.redis import get_redis
            from app.domains.memory.queue_state import memory_brief_pending_key

            await get_redis().delete(memory_brief_pending_key(twin_id))
        except Exception:
            logger.warning(
                "memory_brief_pending_cleanup_failed",
                twin_id=twin_id,
                exc_info=True,
            )


# ─── ARQ worker config ────────────────────────────────────────────────────────


class WorkerSettings:
    """ARQ worker configuration."""
    functions = [ingest_source, generate_memory_brief]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 10
    job_timeout = 600  # 10 min max — memory extraction can take up to 10 min
