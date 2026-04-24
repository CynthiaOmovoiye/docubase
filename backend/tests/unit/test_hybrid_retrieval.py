from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domains.retrieval.hybrid import (
    _fetch_chunk_candidates_by_substring,
    _tokenise_lexical_query,
)
from app.domains.retrieval.intent import QueryIntent
from app.domains.retrieval.router import (
    _SURPLUS_SAME_SOURCE_DEMOTION_FACTOR,
    _demote_surplus_same_source,
    retrieve_packet_for_twin,
)
from app.models.chunk import ChunkType


def test_tokenise_lexical_query_prioritises_long_tokens_and_paths():
    # Tokens with length >= 10 get priority 2; shorter non-path tokens get priority 3.
    # "functionality" (13 chars) and "current_user" (12 chars) are both >= 10, sorted desc by len.
    # "refresh" (7), "logout" (6), "assigned" (8) are < 10 — come after the long tokens.
    tokens = _tokenise_lexical_query(
        "I've been assigned logout functionality. Where do I start? refresh token current_user"
    )
    assert "functionality" in tokens
    assert "current_user" in tokens
    assert "assigned" in tokens
    # Both long tokens appear before short ones
    assert tokens.index("functionality") < tokens.index("assigned")
    assert tokens.index("current_user") < tokens.index("assigned")


@pytest.mark.asyncio
async def test_chunk_substring_fallback_matches_lexical_content():
    db = MagicMock()
    rows = [
        SimpleNamespace(
            id="00000000-0000-0000-0000-000000000001",
            content="Authorization header must include a valid bearer token.",
            chunk_type=ChunkType.documentation,
            source_ref="docs/api.md",
            score=0.64,
        )
    ]
    db.execute = AsyncMock(return_value=SimpleNamespace(fetchall=lambda: rows))

    result = await _fetch_chunk_candidates_by_substring(
        db=db,
        doctwin_id="twin-1",
        lexical_query="authorization bearer token",
        limit=4,
    )

    assert result == rows


@pytest.mark.asyncio
async def test_retrieve_packet_for_twin_fuses_vector_and_lexical():
    db = MagicMock()
    profile = SimpleNamespace(provider="jina", model="jina-embeddings-v3", dimensions=1024)
    vector_row = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001",
        content="Warm database template overview.",
        chunk_type=ChunkType.documentation,
        source_ref="docs/overview.md",
        score=0.82,
    )

    with (
        patch(
            "app.domains.retrieval.router._load_doctwin_embedding_profiles",
            AsyncMock(return_value=[profile]),
        ),
        patch(
            "app.domains.retrieval.router.embed_text_with_profile",
            AsyncMock(return_value=[0.1, 0.2, 0.3]),
        ),
        patch(
            "app.domains.retrieval.router._fetch_doctwin_candidates_for_profile",
            AsyncMock(return_value=[vector_row]),
        ),
        patch(
            "app.domains.retrieval.router.fetch_lexical_chunk_candidates",
            AsyncMock(
                return_value=[
                    {
                        "chunk_id": "00000000-0000-0000-0000-000000000001",
                        "content": "Warm database template overview.",
                        "chunk_type": ChunkType.documentation,
                        "source_ref": "docs/overview.md",
                        "score": 0.71,
                        "match_reasons": ["lexical"],
                    }
                ]
            ),
        ),
        patch(
            "app.domains.retrieval.router.hydrate_retrieved_chunks",
            AsyncMock(
                side_effect=lambda chunks, _db: [
                    {
                        **chunk,
                        "source_id": "source-1",
                        "doctwin_id": "twin-1",
                        "snapshot_id": "snap-1",
                        "start_line": 1,
                        "end_line": 10,
                    }
                    for chunk in chunks
                ]
            ),
        ),
        patch(
            "app.domains.retrieval.router._fetch_by_path_prefix",
            AsyncMock(return_value=[]),
        ),
    ):
        packet = await retrieve_packet_for_twin(
            query="Walk me through the warm database template.",
            doctwin_id="twin-1",
            allow_code_snippets=False,
            db=db,
            top_k=4,
            intent=QueryIntent.specific,
        )

    assert len(packet.chunks) >= 1
    assert packet.chunks[0]["chunk_id"] == "00000000-0000-0000-0000-000000000001"
    assert "vector" in packet.chunks[0]["match_reasons"]
    assert "lexical" in packet.chunks[0]["match_reasons"]


def test_demote_surplus_same_source_penalizes_extra_rows_per_file():
    candidates = [
        {"source_ref": "docs/a.md", "score": 0.9},
        {"source_ref": "docs/a.md", "score": 0.85},
        {"source_ref": "docs/a.md", "score": 0.8},
        {"source_ref": "docs/b.md", "score": 0.5},
    ]
    _demote_surplus_same_source(candidates, max_per_source=2)
    scores_a = sorted(
        (c["score"] for c in candidates if c["source_ref"] == "docs/a.md"),
        reverse=True,
    )
    assert scores_a[0] == 0.9
    assert scores_a[1] == 0.85
    assert scores_a[2] == pytest.approx(0.8 * _SURPLUS_SAME_SOURCE_DEMOTION_FACTOR)
    assert [c["score"] for c in candidates if c["source_ref"] == "docs/b.md"][0] == 0.5
