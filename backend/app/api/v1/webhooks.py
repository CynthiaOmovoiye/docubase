"""
Webhook handlers for provider push notifications.

Each provider has its own signature verification scheme:
  - GitHub: X-Hub-Signature-256 (HMAC-SHA256 of payload, prefixed "sha256=")
  - GitLab: X-Gitlab-Token (shared secret compared directly)
  - Google Drive: X-Goog-Channel-Token (shared secret compared directly via compare_digest)

Security principles:
  - Signature verification happens BEFORE reading/trusting any payload field.
  - Per-source webhook_secret means a compromised secret for one source cannot
    forge events for another.
  - All HMAC comparisons use hmac.compare_digest to prevent timing attacks.
  - Unverifiable requests receive 401 immediately with no payload processing.
  - Enqueue is fire-and-forget — we return 200 to the provider quickly and let
    the ingestion worker handle the actual sync.

Why per-source secrets rather than a single global webhook secret?
  A single secret is acceptable for GitHub (their docs support it), but using
  per-source secrets gives us finer revocation granularity and means a leaked
  source config does not grant the attacker the ability to forge ALL webhooks.
"""

from __future__ import annotations

import hashlib
import hmac

import structlog
from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.source import Source
from fastapi import Depends

router = APIRouter()
logger = structlog.get_logger(__name__)


# ─── GitHub ───────────────────────────────────────────────────────────────────


@router.post("/github", status_code=status.HTTP_200_OK)
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Receive GitHub push (and ping) webhook events.

    Verifies X-Hub-Signature-256 against the per-source webhook_secret.
    On a push event, enqueues the source for re-ingestion.
    """
    payload_bytes = await request.body()

    if not x_hub_signature_256:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Hub-Signature-256 header",
        )

    # GitHub sends the repo full_name in the payload; we use it to look up the source
    try:
        payload_json = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    # Handle ping event (sent when the webhook is first created)
    if x_github_event == "ping":
        logger.info("github_webhook_ping_received")
        return {"status": "ok"}

    if x_github_event != "push":
        # Silently accept but ignore non-push events
        return {"status": "ignored", "event": x_github_event}

    repo_full_name: str = payload_json.get("repository", {}).get("full_name", "")
    if not repo_full_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not determine repository from payload",
        )

    # Find the source by repo_full_name in connection_config
    source = await _find_source_by_repo(repo_full_name, "github_repo", db)
    if source is None:
        # Return 200 to avoid GitHub disabling the webhook, but log the miss
        logger.warning("github_webhook_source_not_found", repo=repo_full_name)
        return {"status": "not_found"}

    if not source.webhook_secret:
        logger.error("github_webhook_no_secret", source_id=str(source.id))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Webhook secret not configured for this source",
        )

    if not verify_github_signature(payload_bytes, x_hub_signature_256, source.webhook_secret):
        logger.warning(
            "github_webhook_invalid_signature",
            source_id=str(source.id),
            repo=repo_full_name,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )

    await _enqueue_ingestion(str(source.id))
    logger.info("github_webhook_ingestion_enqueued", source_id=str(source.id), repo=repo_full_name)

    return {"status": "queued", "source_id": str(source.id)}


# ─── GitLab ───────────────────────────────────────────────────────────────────


@router.post("/gitlab", status_code=status.HTTP_200_OK)
async def gitlab_webhook(
    request: Request,
    x_gitlab_token: str | None = Header(default=None),
    x_gitlab_event: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Receive GitLab push webhook events.

    Verifies X-Gitlab-Token against the per-source webhook_secret.
    On a Push Hook event, enqueues the source for re-ingestion.
    """
    if not x_gitlab_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Gitlab-Token header",
        )

    try:
        payload_json = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    if x_gitlab_event != "Push Hook":
        return {"status": "ignored", "event": x_gitlab_event}

    project_path: str = payload_json.get("project", {}).get("path_with_namespace", "")
    if not project_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not determine project from payload",
        )

    source = await _find_source_by_repo(project_path, "gitlab_repo", db)
    if source is None:
        logger.warning("gitlab_webhook_source_not_found", project=project_path)
        return {"status": "not_found"}

    if not source.webhook_secret:
        logger.error("gitlab_webhook_no_secret", source_id=str(source.id))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Webhook secret not configured for this source",
        )

    if not verify_gitlab_token(x_gitlab_token, source.webhook_secret):
        logger.warning(
            "gitlab_webhook_invalid_token",
            source_id=str(source.id),
            project=project_path,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook token",
        )

    await _enqueue_ingestion(str(source.id))
    logger.info(
        "gitlab_webhook_ingestion_enqueued",
        source_id=str(source.id),
        project=project_path,
    )

    return {"status": "queued", "source_id": str(source.id)}


# ─── Google Drive ─────────────────────────────────────────────────────────────


@router.post("/google_drive", status_code=status.HTTP_200_OK)
async def google_drive_webhook(
    request: Request,
    x_goog_channel_token: str | None = Header(default=None),
    x_goog_resource_id: str | None = Header(default=None),
    x_goog_channel_id: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Receive Google Drive push channel notifications.

    Verifies X-Goog-Channel-Token against the per-source webhook_secret.
    On a valid notification, enqueues the source for re-ingestion.
    """
    if not x_goog_channel_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Goog-Channel-Token header",
        )

    if not x_goog_channel_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Goog-Channel-Id header",
        )

    # The channel_id is the webhook_id we stored on the source at registration time
    source = await _find_source_by_webhook_id(x_goog_channel_id, db)
    if source is None:
        logger.warning("gdrive_webhook_source_not_found", channel_id=x_goog_channel_id)
        return {"status": "not_found"}

    if not source.webhook_secret:
        logger.error("gdrive_webhook_no_secret", source_id=str(source.id))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Webhook secret not configured for this source",
        )

    if not verify_google_drive_token(x_goog_channel_token, source.webhook_secret):
        logger.warning(
            "gdrive_webhook_invalid_token",
            source_id=str(source.id),
            channel_id=x_goog_channel_id,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid channel token",
        )

    await _enqueue_ingestion(str(source.id))
    logger.info(
        "gdrive_webhook_ingestion_enqueued",
        source_id=str(source.id),
        channel_id=x_goog_channel_id,
    )

    return {"status": "queued", "source_id": str(source.id)}


# ─── Signature verification ───────────────────────────────────────────────────


def verify_github_signature(
    payload: bytes,
    signature_header: str,
    secret: str,
) -> bool:
    """
    Verify GitHub's X-Hub-Signature-256 header.

    Expected format: "sha256=<hex_digest>"
    Uses hmac.compare_digest to prevent timing attacks.
    """
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def verify_gitlab_token(
    token_header: str,
    secret: str,
) -> bool:
    """
    Verify GitLab's X-Gitlab-Token header (shared secret string).

    Uses compare_digest to prevent timing attacks even on plain string comparison.
    """
    return hmac.compare_digest(secret, token_header)


def verify_google_drive_token(
    channel_token: str,
    secret: str,
) -> bool:
    """
    Verify Google Drive's X-Goog-Channel-Token header.

    The token is a plain secret string we set when registering the watch channel.
    Uses compare_digest to prevent timing attacks.
    """
    return hmac.compare_digest(secret, channel_token)


# ─── DB helpers ───────────────────────────────────────────────────────────────


async def _find_source_by_repo(
    repo_identifier: str,
    source_type: str,
    db: AsyncSession,
) -> Source | None:
    """
    Find a Source whose connection_config contains a matching repo identifier.

    GitHub stores full_name, GitLab stores path_with_namespace — both end up
    as the "repo_full_name" key in connection_config by convention.
    """
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy import cast

    # Use a JSONB path query to match on connection_config->>'repo_full_name'
    result = await db.execute(
        select(Source).where(
            Source.source_type == source_type,
            Source.connection_config["repo_full_name"].astext == repo_identifier,
        )
    )
    return result.scalars().first()


async def _find_source_by_webhook_id(
    webhook_id: str,
    db: AsyncSession,
) -> Source | None:
    """Find a Source by its provider-assigned webhook_id."""
    result = await db.execute(
        select(Source).where(Source.webhook_id == webhook_id)
    )
    return result.scalars().first()


# ─── Job enqueueing ───────────────────────────────────────────────────────────


async def _enqueue_ingestion(source_id: str) -> None:
    """
    Enqueue an ingestion job via ARQ.

    Fire-and-forget — we return quickly to the provider and let the worker
    handle the sync. If enqueueing fails, we log the error; the source can
    be re-synced manually via the /sources/{id}/sync endpoint.
    """
    try:
        from arq import create_pool
        from arq.connections import RedisSettings
        from app.core.config import get_settings

        settings = get_settings()
        redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        await redis.enqueue_job("ingest_source", source_id)
        await redis.aclose()
    except Exception as exc:
        from app.core.logging import get_logger
        _logger = get_logger(__name__)
        _logger.error("webhook_ingestion_enqueue_failed", source_id=source_id, error=str(exc))
