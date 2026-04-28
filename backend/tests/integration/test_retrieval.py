"""Hybrid retrieval returns indexed chunks from Postgres-backed vectors."""

from app.domains.retrieval.intent import QueryIntent
from app.domains.retrieval.router import retrieve_packet_for_twin

from .helpers import (
    create_manual_source_row,
    create_owner_workspace_twin,
    ingest_manual_full_sync,
)


async def test_retrieve_packet_returns_matching_chunk(db_session):
    scenario = await create_owner_workspace_twin(db_session)
    marker = "INTEGRATION_RETRIEVAL_UNIQUE_BRAVO"
    src = await create_manual_source_row(
        db_session,
        twin_id=scenario.twin_id,
        title="Docs",
        body=f"# Spec\n\nRequirement: {marker} must be discoverable.",
    )
    await ingest_manual_full_sync(db_session, scenario=scenario, source=src)
    await db_session.commit()

    packet = await retrieve_packet_for_twin(
        query=f"What about {marker}?",
        doctwin_id=str(scenario.twin_id),
        allow_code_snippets=False,
        db=db_session,
        top_k=8,
        intent=QueryIntent.general,
        path_hints=[],
        guaranteed_refs=[],
        expanded_query="",
        pipeline_trace_id=None,
    )

    merged = " ".join((c.get("content") or "") for c in packet.chunks)
    assert marker in merged
