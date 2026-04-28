"""Incremental (delta) connector semantics via ``process_connector_result``."""

from sqlalchemy import select

from app.connectors.base import ConnectorResult, RawFile
from app.models.chunk import Chunk

from .helpers import (
    create_manual_source_row,
    create_owner_workspace_twin,
    ingest_raw_result,
)


async def test_delta_sync_removes_deleted_paths_and_indexes_new_files(db_session):
    scenario = await create_owner_workspace_twin(db_session)
    src = await create_manual_source_row(
        db_session,
        twin_id=scenario.twin_id,
        title="unused-for-delta",
        body="placeholder",
    )
    await db_session.flush()

    first = ConnectorResult(
        source_id=str(src.id),
        files=[
            RawFile(
                path="sync/first.md",
                content="FIRST_DELTA_UNIQUE_XRAY",
                size_bytes=len("FIRST_DELTA_UNIQUE_XRAY"),
                metadata={},
            ),
        ],
        is_full_sync=True,
    )
    await ingest_raw_result(
        db_session,
        doctwin_id=scenario.twin_id,
        source_id=src.id,
        result=first,
        clear_first_if_full=True,
    )

    second = ConnectorResult(
        source_id=str(src.id),
        files=[
            RawFile(
                path="sync/second.md",
                content="SECOND_DELTA_UNIQUE_YANK",
                size_bytes=len("SECOND_DELTA_UNIQUE_YANK"),
                metadata={},
            ),
        ],
        is_full_sync=False,
        deleted_paths=["sync/first.md"],
    )
    await ingest_raw_result(
        db_session,
        doctwin_id=scenario.twin_id,
        source_id=src.id,
        result=second,
        clear_first_if_full=False,
    )
    await db_session.commit()

    rows = (
        await db_session.execute(select(Chunk).where(Chunk.source_id == src.id))
    ).scalars().all()

    corpus = " ".join(r.content for r in rows)
    assert "FIRST_DELTA_UNIQUE_XRAY" not in corpus
    assert "SECOND_DELTA_UNIQUE_YANK" in corpus
