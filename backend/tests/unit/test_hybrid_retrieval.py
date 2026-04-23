from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domains.retrieval.hybrid import (
    HybridMatches,
    _fetch_chunk_candidates_by_substring,
    _tokenise_lexical_query,
)
from app.domains.retrieval.intent import QueryIntent
from app.domains.retrieval.packets import EvidenceFileRef, EvidenceSymbolRef
from app.domains.retrieval.router import (
    _SURPLUS_SAME_SOURCE_DEMOTION_FACTOR,
    _demote_surplus_same_source,
    _feature_priority_sort_value,
    retrieve_packet_for_twin,
)
from app.models.chunk import ChunkType


def test_tokenise_lexical_query_prioritises_domain_tokens_over_filler():
    tokens = _tokenise_lexical_query(
        "I've been assigned logout functionality. Where do I start? refresh token current_user"
    )

    assert tokens.index("current_user") < tokens.index("functionality")
    assert tokens.index("refresh") < tokens.index("assigned")
    assert tokens.index("logout") < tokens.index("assigned")


def test_feature_priority_sort_value_preserves_zero_priority():
    ordered = sorted(
        [
            {"_feature_priority": 3, "source_ref": "scaffold/api/v1/routes/auth.py"},
            {"_feature_priority": 0, "source_ref": "scaffold/core/auth.py"},
            {"source_ref": "docs/architecture.md"},
        ],
        key=_feature_priority_sort_value,
    )

    assert [item["source_ref"] for item in ordered] == [
        "scaffold/core/auth.py",
        "scaffold/api/v1/routes/auth.py",
        "docs/architecture.md",
    ]


@pytest.mark.asyncio
async def test_chunk_substring_fallback_can_match_auth_tokens_in_code_content():
    db = MagicMock()
    rows = [
        SimpleNamespace(
            id="00000000-0000-0000-0000-000000000001",
            content="if project.owner_id != current_user.id: raise HTTPException(status_code=404)",
            chunk_type=ChunkType.code_snippet,
            source_ref="scaffold/api/v1/routes/projects.py",
            score=0.64,
        )
    ]

    db.execute = AsyncMock(return_value=SimpleNamespace(fetchall=lambda: rows))

    result = await _fetch_chunk_candidates_by_substring(
        db=db,
        twin_id="twin-1",
        lexical_query="authorization current_user owner_id",
        allow_code_snippets=True,
        limit=4,
    )

    assert result == rows


@pytest.mark.asyncio
async def test_retrieve_packet_for_twin_fuses_hybrid_layers():
    db = MagicMock()
    profile = SimpleNamespace(provider="jina", model="jina-embeddings-v3", dimensions=1024)
    vector_row = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001",
        content="async def login_user(payload): ...",
        chunk_type=ChunkType.code_snippet,
        source_ref="app/auth.py",
        score=0.82,
    )

    with (
        patch(
            "app.domains.retrieval.router._load_twin_embedding_profiles",
            AsyncMock(return_value=[profile]),
        ),
        patch(
            "app.domains.retrieval.router.embed_text_with_profile",
            AsyncMock(return_value=[0.1, 0.2, 0.3]),
        ),
        patch(
            "app.domains.retrieval.router._fetch_twin_candidates_for_profile",
            AsyncMock(return_value=[vector_row]),
        ),
        patch(
            "app.domains.retrieval.router.fetch_lexical_chunk_candidates",
            AsyncMock(
                return_value=[
                    {
                        "chunk_id": "00000000-0000-0000-0000-000000000001",
                        "content": "async def login_user(payload): ...",
                        "chunk_type": ChunkType.code_snippet,
                        "source_ref": "app/auth.py",
                        "score": 0.71,
                        "match_reasons": ["lexical"],
                    }
                ]
            ),
        ),
        patch(
            "app.domains.retrieval.router.fetch_file_candidates",
            AsyncMock(
                return_value=HybridMatches(
                    chunks=[],
                    files=[
                        EvidenceFileRef(
                            path="app/auth.py",
                            twin_id="twin-1",
                            source_id="source-1",
                            snapshot_id="snap-1",
                            reasons=["file"],
                        )
                    ],
                    symbols=[],
                )
            ),
        ),
        patch(
            "app.domains.retrieval.router.fetch_symbol_candidates",
            AsyncMock(
                return_value=HybridMatches(
                    chunks=[
                        {
                            "chunk_id": "00000000-0000-0000-0000-000000000001",
                            "content": "async def login_user(payload): ...",
                            "chunk_type": ChunkType.code_snippet,
                            "source_ref": "app/auth.py",
                            "score": 0.88,
                            "match_reasons": ["symbol:login_user"],
                        }
                    ],
                    files=[],
                    symbols=[
                        EvidenceSymbolRef(
                            symbol_name="login_user",
                            qualified_name="login_user",
                            symbol_kind="async_function",
                            path="app/auth.py",
                            twin_id="twin-1",
                            source_id="source-1",
                            snapshot_id="snap-1",
                            reasons=["symbol"],
                        )
                    ],
                )
            ),
        ),
        patch(
            "app.domains.retrieval.router.multihop_retrieve_with_graph",
            AsyncMock(
                return_value=(
                    [
                        {
                            "chunk_id": "00000000-0000-0000-0000-000000000002",
                            "content": "router.post('/login')",
                            "chunk_type": ChunkType.module_description,
                            "source_ref": "app/auth.py",
                            "score": 0.5,
                        }
                    ],
                    [
                        {
                            "source": "AuthRouter",
                            "target": "login_user",
                            "relationship_type": "uses",
                        }
                    ],
                )
            ),
        ),
        patch(
            "app.domains.retrieval.router.reranker_available",
            return_value=False,
        ),
        patch(
            "app.domains.retrieval.router.hydrate_retrieved_chunks",
            AsyncMock(
                side_effect=lambda chunks, _db: [
                    {
                        **chunk,
                        "source_id": "source-1",
                        "twin_id": "twin-1",
                        "snapshot_id": "snap-1",
                        "start_line": 10,
                        "end_line": 20,
                    }
                    for chunk in chunks
                ]
            ),
        ),
        patch(
            "app.domains.retrieval.router.search_implementation_facts_for_twin",
            AsyncMock(return_value=[]),
        ),
    ):
        packet = await retrieve_packet_for_twin(
            query="How is authentication implemented?",
            twin_id="twin-1",
            allow_code_snippets=True,
            db=db,
            top_k=4,
            intent=QueryIntent.file_specific,
            expanded_query=(
                "Explain the authentication implementation and the specific files "
                "and symbols involved."
            ),
        )

    assert packet.mode.value == "implementation"
    assert packet.search_query.startswith("Explain the authentication implementation")
    assert packet.chunk_ids == [
        "00000000-0000-0000-0000-000000000001",
        "00000000-0000-0000-0000-000000000002",
    ]
    assert packet.symbols[0].qualified_name == "login_user"
    assert packet.files[0].path == "app/auth.py"
    assert packet.graph_edges[0]["source"] == "AuthRouter"
    first_chunk = packet.chunks[0]
    assert "vector" in first_chunk["match_reasons"]
    assert "lexical" in first_chunk["match_reasons"]
    assert "symbol:login_user" in first_chunk["match_reasons"]
    assert "facts" in packet.searched_layers


@pytest.mark.asyncio
async def test_retrieve_packet_for_twin_demotes_memory_and_meta_docs_for_implementation_queries():
    db = MagicMock()
    profile = SimpleNamespace(provider="jina", model="jina-embeddings-v3", dimensions=1024)
    memory_row = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001",
        content="Authentication summary from memory brief.",
        chunk_type=ChunkType.auth_flow,
        source_ref="__memory__/twin-1",
        score=0.97,
    )
    doc_row = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000002",
        content="Architecture document describing integrations.",
        chunk_type=ChunkType.documentation,
        source_ref="docs/Scaffold_Technical_Architecture_v1.0.docx",
        score=0.93,
    )

    with (
        patch(
            "app.domains.retrieval.router._load_twin_embedding_profiles",
            AsyncMock(return_value=[profile]),
        ),
        patch(
            "app.domains.retrieval.router.embed_text_with_profile",
            AsyncMock(return_value=[0.1, 0.2, 0.3]),
        ),
        patch(
            "app.domains.retrieval.router._fetch_twin_candidates_for_profile",
            AsyncMock(return_value=[memory_row, doc_row]),
        ),
        patch(
            "app.domains.retrieval.router.fetch_lexical_chunk_candidates",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.domains.retrieval.router.fetch_file_candidates",
            AsyncMock(
                return_value=HybridMatches(
                    chunks=[
                        {
                            "chunk_id": "00000000-0000-0000-0000-000000000003",
                            "content": "clearAuth removes tokens from local storage.",
                            "chunk_type": ChunkType.code_snippet,
                            "source_ref": "frontend/src/lib/auth.ts",
                            "score": 0.71,
                            "match_reasons": ["file"],
                        }
                    ],
                    files=[
                        EvidenceFileRef(
                            path="frontend/src/lib/auth.ts",
                            twin_id="twin-1",
                            source_id="source-1",
                            snapshot_id="snap-1",
                            reasons=["file"],
                        )
                    ],
                    symbols=[],
                )
            ),
        ),
        patch(
            "app.domains.retrieval.router.fetch_symbol_candidates",
            AsyncMock(
                return_value=HybridMatches(
                    chunks=[
                        {
                            "chunk_id": "00000000-0000-0000-0000-000000000004",
                            "content": "clearAuth removes the access and refresh tokens.",
                            "chunk_type": ChunkType.module_description,
                            "source_ref": "frontend/src/lib/auth.ts",
                            "score": 0.76,
                            "match_reasons": ["symbol:clearAuth"],
                        }
                    ],
                    files=[],
                    symbols=[
                        EvidenceSymbolRef(
                            symbol_name="clearAuth",
                            qualified_name="clearAuth",
                            symbol_kind="function",
                            path="frontend/src/lib/auth.ts",
                            twin_id="twin-1",
                            source_id="source-1",
                            snapshot_id="snap-1",
                            reasons=["symbol"],
                        )
                    ],
                )
            ),
        ),
        patch(
            "app.domains.retrieval.router.multihop_retrieve_with_graph",
            AsyncMock(return_value=([], [])),
        ),
        patch(
            "app.domains.retrieval.router.reranker_available",
            return_value=False,
        ),
        patch(
            "app.domains.retrieval.router.hydrate_retrieved_chunks",
            AsyncMock(side_effect=lambda chunks, _db: chunks),
        ),
        patch(
            "app.domains.retrieval.router.search_implementation_facts_for_twin",
            AsyncMock(return_value=[]),
        ),
    ):
        packet = await retrieve_packet_for_twin(
            query="Explain the authentication flow and provide code snippets where necessary.",
            twin_id="twin-1",
            allow_code_snippets=True,
            db=db,
            top_k=4,
            intent=QueryIntent.general,
        )

    assert packet.mode.value == "implementation"
    assert packet.chunks[0]["source_ref"] == "frontend/src/lib/auth.ts"
    assert all(
        chunk["source_ref"] != "docs/Scaffold_Technical_Architecture_v1.0.docx"
        for chunk in packet.chunks[:2]
    )
    assert all(file_ref.path != "__memory__/twin-1" for file_ref in packet.files)


def test_demote_surplus_same_source_penalizes_extra_rows_per_file():
    candidates = [
        {"source_ref": "app/a.py", "score": 0.9},
        {"source_ref": "app/a.py", "score": 0.85},
        {"source_ref": "app/a.py", "score": 0.8},
        {"source_ref": "app/b.py", "score": 0.5},
    ]
    _demote_surplus_same_source(candidates, max_per_source=2)
    scores_a = sorted(
        (c["score"] for c in candidates if c["source_ref"] == "app/a.py"),
        reverse=True,
    )
    assert scores_a[0] == 0.9
    assert scores_a[1] == 0.85
    assert scores_a[2] == pytest.approx(0.8 * _SURPLUS_SAME_SOURCE_DEMOTION_FACTOR)
    assert [c["score"] for c in candidates if c["source_ref"] == "app/b.py"][0] == 0.5
