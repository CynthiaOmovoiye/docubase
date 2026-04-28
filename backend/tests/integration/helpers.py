"""
Factories for integration tests — insert minimal rows via SQLAlchemy.

Avoid importing FastAPI routers; use domain services and pipeline directly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.base import ConnectorResult
from app.connectors.manual.connector import ManualConnector
from app.core.security import hash_password
from app.domains.knowledge.pipeline import clear_chunks_for_source, process_connector_result
from app.domains.sources.service import mark_source_ready
from app.models.source import Source, SourceStatus, SourceType
from app.models.twin import Twin, TwinConfig
from app.models.user import User
from app.models.workspace import Workspace


@dataclass(slots=True)
class IntegrationScenario:
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    twin_id: uuid.UUID


async def create_owner_workspace_twin(
    db: AsyncSession,
    *,
    slug_suffix: str | None = None,
) -> IntegrationScenario:
    """Owner user + workspace + twin + TwinConfig row."""
    suf = slug_suffix or uuid.uuid4().hex[:12]

    user = User(
        email=f"integration-{suf}@docbase.test.invalid",
        hashed_password=hash_password("integration-test-password"),
        display_name="Integration Tester",
        is_active=True,
        is_verified=True,
        is_superuser=False,
    )
    db.add(user)
    await db.flush()

    ws = Workspace(
        name=f"Integration Workspace {suf}",
        slug=f"iw-{suf}",
        description=None,
        owner_id=user.id,
    )
    db.add(ws)
    await db.flush()

    twin = Twin(
        name=f"Integration Twin {suf}",
        slug=f"twin-{suf}",
        description=None,
        is_active=True,
        workspace_id=ws.id,
    )
    db.add(twin)
    await db.flush()

    cfg = TwinConfig(
        doctwin_id=twin.id,
        allow_code_snippets=False,
        is_public=False,
        custom_context=None,
        memory_brief=None,
        memory_brief_status=None,
        memory_brief_generated_at=None,
        extra={},
    )
    db.add(cfg)

    await db.flush()

    return IntegrationScenario(
        user_id=user.id,
        workspace_id=ws.id,
        twin_id=twin.id,
    )


async def create_manual_source_row(
    db: AsyncSession,
    *,
    twin_id: uuid.UUID,
    title: str,
    body: str,
    source_name: str = "manual-notes",
) -> Source:
    src = Source(
        name=source_name,
        source_type=SourceType.manual,
        status=SourceStatus.pending,
        doctwin_id=twin_id,
        connection_config={
            "content": body,
            "title": title,
        },
        index_health={},
    )
    db.add(src)
    await db.flush()
    await db.refresh(src)
    return src


async def ingest_manual_full_sync(
    db: AsyncSession,
    *,
    scenario: IntegrationScenario,
    source: Source,
) -> dict:
    """Full-sync ingest via ManualConnector + pipeline + mark ready."""
    connector = ManualConnector()
    cfg = dict(source.connection_config or {})
    cfg["source_id"] = str(source.id)
    await connector.validate_connection(cfg)
    result = await connector.fetch(cfg)
    result.source_id = str(source.id)
    result.is_full_sync = True

    await clear_chunks_for_source(str(source.id), db)
    stats = await process_connector_result(
        result,
        str(scenario.twin_id),
        False,
        db,
    )
    await mark_source_ready(str(source.id), db)
    return stats


async def ingest_raw_result(
    db: AsyncSession,
    *,
    doctwin_id: uuid.UUID,
    source_id: uuid.UUID,
    result: ConnectorResult,
    clear_first_if_full: bool = False,
) -> dict:
    """Lower-level ingest used for scripted ConnectorResult (delta sync tests)."""
    result.source_id = str(source_id)
    if clear_first_if_full and result.is_full_sync:
        await clear_chunks_for_source(str(source_id), db)
    stats = await process_connector_result(result, str(doctwin_id), False, db)
    await mark_source_ready(str(source_id), db)
    return stats


async def count_chunks_for_source(db: AsyncSession, source_id: uuid.UUID) -> int:
    from sqlalchemy import func

    from app.models.chunk import Chunk

    q = await db.execute(select(func.count()).select_from(Chunk).where(Chunk.source_id == source_id))
    return int(q.scalar_one())
