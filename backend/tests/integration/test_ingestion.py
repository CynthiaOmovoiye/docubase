"""Knowledge pipeline persists chunks + embeddings for a manual source."""

from sqlalchemy import select

from app.models.chunk import Chunk

from .helpers import (
    create_manual_source_row,
    create_owner_workspace_twin,
    ingest_manual_full_sync,
)


async def test_manual_ingestion_writes_chunks_with_embeddings(db_session):
    scenario = await create_owner_workspace_twin(db_session)
    token = "INTEGRATION_INGEST_UNIQUE_ALPHA"
    src = await create_manual_source_row(
        db_session,
        twin_id=scenario.twin_id,
        title="Integration Notes",
        body=f"# Hello\n\nThis paragraph states {token} for retrieval testing.",
    )
    stats = await ingest_manual_full_sync(db_session, scenario=scenario, source=src)
    await db_session.commit()

    assert stats["chunks_created"] >= 1
    assert stats["chunks_embedded"] >= 1

    rows = (
        await db_session.execute(
            select(Chunk).where(Chunk.source_id == src.id),
        )
    ).scalars().all()

    assert len(rows) >= 1
    contents = " ".join((r.content or "") for r in rows)
    assert token in contents
    assert rows[0].embedding is not None
    assert len(rows[0].embedding) > 0
