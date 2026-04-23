#!/usr/bin/env python3
"""
reset_and_regen_memory.py
─────────────────────────
Reset engineering memory for a twin and trigger a full re-ingestion + brief
generation cycle.  Run this from the backend/ directory:

    uv run python scripts/reset_and_regen_memory.py <twin_id>

What it does:
  1. Clears all __memory__ chunks for the twin
  2. Clears the phantom __memory__ source anchor row
  3. Resets twin_configs.memory_brief / memory_brief_status / memory_brief_generated_at
  4. Resets last_commit_sha on all git sources (forces full re-sync, not delta)
  5. Enqueues ingest_source for every ready/failed source on the twin
     (ingest_source will auto-enqueue generate_memory_brief when complete)
  6. Polls the twin config every 10 s until memory_brief_status changes to
     "ready" or "failed" (or 15-minute timeout)

Requires the .env file at the project root (or environment variables already set).
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap .env — look one level up from backend/
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent.parent  # docubase/
_ENV_FILE = _ROOT / ".env"
if _ENV_FILE.exists():
    from dotenv import load_dotenv  # type: ignore[import]
    load_dotenv(_ENV_FILE, override=False)
    print(f"[env] Loaded {_ENV_FILE}")
else:
    print(f"[warn] .env not found at {_ENV_FILE} — assuming env vars are already set")

# ---------------------------------------------------------------------------
# Imports (after env vars are available)
# ---------------------------------------------------------------------------
import uuid as _uuid

from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.models.chunk import Chunk
from app.models.source import Source, SourceStatus
from app.models.twin import TwinConfig

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def reset_twin(twin_id_str: str) -> None:
    settings = get_settings()
    twin_id = _uuid.UUID(twin_id_str)

    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)  # type: ignore[call-overload]

    async with async_session() as db:
        # ── 1. Delete all __memory__ chunks ──────────────────────────────────
        memory_ref = f"__memory__/{twin_id_str}"
        result = await db.execute(
            delete(Chunk).where(Chunk.source_ref == memory_ref).returning(Chunk.id)
        )
        deleted_chunks = len(result.fetchall())
        print(f"[reset] Deleted {deleted_chunks} memory chunks")

        # ── 2. Delete the phantom __memory__ source anchor ───────────────────
        synthetic_source_id = _uuid.uuid5(_uuid.NAMESPACE_DNS, f"memory:{twin_id_str}")
        result2 = await db.execute(
            delete(Source).where(Source.id == synthetic_source_id).returning(Source.id)
        )
        deleted_sources = len(result2.fetchall())
        print(f"[reset] Deleted {deleted_sources} phantom source row(s)")

        # ── 3. Clear memory brief on TwinConfig ──────────────────────────────
        await db.execute(
            update(TwinConfig)
            .where(TwinConfig.twin_id == twin_id)
            .values(
                memory_brief=None,
                memory_brief_status=None,
                memory_brief_generated_at=None,
            )
        )
        print("[reset] Cleared memory_brief on twin_config")

        # ── 4. Reset last_commit_sha on git sources (force full re-sync) ─────
        sources_result = await db.execute(
            select(Source).where(
                Source.twin_id == twin_id,
                Source.name != "__memory__",
            )
        )
        sources = sources_result.scalars().all()
        print(f"[reset] Found {len(sources)} source(s) on twin")

        for src in sources:
            src.last_commit_sha = None
            src.last_page_token = None
            print(f"  → Reset {src.source_type.value} source: {src.name} ({src.id})")

        await db.commit()
        print("[reset] All resets committed ✓")

        # ── 5. Enqueue ingest_source for each source ─────────────────────────
        redis_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        enqueued = 0
        for src in sources:
            # Mark pending before re-queuing
            src.status = SourceStatus.pending
            await db.commit()
            await redis_pool.enqueue_job("ingest_source", str(src.id))
            print(f"  → Enqueued ingest_source for {src.id}")
            enqueued += 1
        await redis_pool.aclose()
        print(f"[reset] Enqueued {enqueued} ingestion job(s)")

    # ── 6. Poll for completion ────────────────────────────────────────────────
    print("\n[poll] Waiting for memory brief generation...")
    print("       (ingest_source → [auto] → generate_memory_brief)")
    print("       Polling every 10 s, timeout 15 min\n")

    timeout = 900  # 15 minutes
    interval = 10
    start = time.time()

    timed_out = True
    while time.time() - start < timeout:
        await asyncio.sleep(interval)
        elapsed = int(time.time() - start)

        # Open a fresh session per poll — reusing one session hits SQLAlchemy's
        # identity-map cache and returns the stale None value even after the
        # worker commits the "ready" status on the other side.
        async with async_session() as db:
            result = await db.execute(
                select(TwinConfig).where(TwinConfig.twin_id == twin_id)
            )
            config = result.scalar_one_or_none()

        status = config.memory_brief_status if config else None
        print(f"  [{elapsed:>4}s] memory_brief_status = {status!r}")

        if status == "ready":
            brief_len = len(config.memory_brief or "")
            print(f"\n✅  Memory brief generated! ({brief_len} chars)")
            print(f"    Generated at: {config.memory_brief_generated_at}")
            print(f"\n--- Brief preview (first 500 chars) ---")
            print((config.memory_brief or "")[:500])
            print("---")
            timed_out = False
            break
        elif status == "failed":
            print(f"\n❌  Generation failed. Check worker logs.")
            await engine.dispose()
            sys.exit(1)

    if timed_out:
        print(f"\n⏱  Timed out after {timeout}s. Check worker logs.")
        await engine.dispose()
        sys.exit(1)

    await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: uv run python scripts/reset_and_regen_memory.py <twin_id>")
        sys.exit(1)

    twin_id_arg = sys.argv[1]
    try:
        _uuid.UUID(twin_id_arg)
    except ValueError:
        print(f"Error: {twin_id_arg!r} is not a valid UUID")
        sys.exit(1)

    asyncio.run(reset_twin(twin_id_arg))
