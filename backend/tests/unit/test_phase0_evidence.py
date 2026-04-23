from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domains.knowledge.evidence import (
    build_index_health,
    build_root_hash,
    build_segment_id,
    classify_chunk_lineage,
    hash_text,
    is_strict_chunk_ready,
    resolve_snapshot_id,
)
from app.domains.retrieval.hydration import hydrate_retrieved_chunks
from app.models.chunk import ChunkLineage, ChunkType
from app.models.source import SourceIndexMode, SourceType


class TestEvidenceHelpers:
    def test_classifies_memory_and_repo_chunks(self):
        assert (
            classify_chunk_lineage(ChunkType.memory_brief, SourceType.google_drive)
            == ChunkLineage.memory_derived
        )
        assert (
            classify_chunk_lineage(ChunkType.code_snippet, SourceType.google_drive)
            == ChunkLineage.file_backed
        )
        assert (
            classify_chunk_lineage(ChunkType.documentation, SourceType.pdf)
            == ChunkLineage.file_backed
        )

    def test_build_segment_id_prefers_line_span(self):
        segment_id = build_segment_id("app/auth.py", ChunkType.code_snippet, 10, 24)
        assert segment_id == "app/auth.py:10-24:code_snippet"

    def test_resolve_snapshot_id_prefers_head_sha_then_root_hash(self):
        assert (
            resolve_snapshot_id({}, "a" * 40, None, "deadbeef")
            == "a" * 40
        )
        assert (
            resolve_snapshot_id({}, None, None, "deadbeef")
            == "hash:deadbeef"
        )

    def test_root_hash_is_deterministic(self):
        left = build_root_hash([("b.py", "bbb"), ("a.py", "aaa")])
        right = build_root_hash([("a.py", "aaa"), ("b.py", "bbb")])
        assert left == right

    def test_build_index_health_marks_legacy_when_support_missing(self):
        health = build_index_health(
            source_type=SourceType.manual,
            snapshot_id="hash:abc",
            snapshot_root_hash="abc",
            stats={"files_received": 1, "files_processed": 1, "chunks_created": 2, "chunks_embedded": 2},
            strict_chunk_total=2,
            strict_chunk_ready=2,
            total_chunks=2,
        )

        assert health["index_mode"] == SourceIndexMode.legacy.value
        assert health["strict_evidence_ready"] is False
        assert health["legacy_reasons"]

    def test_pdf_and_drive_now_support_strict_evidence(self):
        for source_type in (SourceType.pdf, SourceType.google_drive):
            health = build_index_health(
                source_type=source_type,
                snapshot_id="hash:abc",
                snapshot_root_hash="abc",
                stats={"files_received": 1, "files_processed": 1, "chunks_created": 1, "chunks_embedded": 1},
                strict_chunk_total=1,
                strict_chunk_ready=1,
                total_chunks=1,
            )

            assert health["index_mode"] == SourceIndexMode.strict.value
            assert health["strict_evidence_ready"] is True

    def test_connector_segments_require_spans_for_strict_mode(self):
        assert is_strict_chunk_ready(
            lineage=ChunkLineage.connector_segment,
            snapshot_id="hash:abc",
            content_hash="deadbeef",
            start_line=1,
            end_line=3,
            segment_id="README.md:1-3:documentation",
        )
        assert not is_strict_chunk_ready(
            lineage=ChunkLineage.connector_segment,
            snapshot_id="hash:abc",
            content_hash="deadbeef",
            start_line=None,
            end_line=None,
            segment_id="README.md:documentation",
        )


class TestHydration:
    @pytest.mark.asyncio
    async def test_hydrates_strict_code_snippet_when_hash_matches(self):
        chunk_id = "0f6754b8-ff73-4f33-9f90-2b09f3b3536d"
        snippet = "# app/auth.py — def login\n\ndef login():\n    return True"
        chunk_row = SimpleNamespace(
            id=chunk_id,
            chunk_type=ChunkType.code_snippet,
            start_line=1,
            end_line=2,
            source_ref="app/auth.py",
            snapshot_id="a" * 40,
            segment_id="app/auth.py:1-2:code_snippet",
            content_hash="1c06351bb74e83597d21454ba3c348ca9e17fce87954b713a7827c6420adea67",
            lineage=ChunkLineage.file_backed,
            chunk_metadata={"symbol_name": "def login"},
        )
        source = SimpleNamespace(
            id="source-1",
            index_mode=SourceIndexMode.strict,
            source_type=SourceType.google_drive,
            connection_config={"file_id": "x", "file_path": "app/auth.py"},
            snapshot_id="a" * 40,
            last_commit_sha="a" * 40,
            connected_account_id="account-1",
            index_health={"policy": {"allow_code_snippets": True}},
        )
        db = MagicMock()
        result = MagicMock()
        result.fetchall.return_value = [SimpleNamespace(Chunk=chunk_row, Source=source)]
        db.execute = AsyncMock(return_value=result)

        with patch(
            "app.domains.retrieval.hydration._load_canonical_source_text",
            AsyncMock(return_value="def login():\n    return True\n"),
        ):
            hydrated = await hydrate_retrieved_chunks(
                [{"chunk_id": chunk_id, "content": "stale", "chunk_type": "code_snippet"}],
                db,
            )

        assert hydrated[0]["content"] == snippet
        assert hydrated[0]["hydrated"] is True

    @pytest.mark.asyncio
    async def test_leaves_chunk_unchanged_when_hash_mismatches(self):
        chunk_id = "d3f41f31-a8c2-4fb3-aed8-ea3592f1f7be"
        chunk_row = SimpleNamespace(
            id=chunk_id,
            chunk_type=ChunkType.code_snippet,
            start_line=1,
            end_line=2,
            source_ref="app/auth.py",
            snapshot_id="a" * 40,
            segment_id="app/auth.py:1-2:code_snippet",
            content_hash="not-a-real-hash",
            lineage=ChunkLineage.file_backed,
            chunk_metadata={"symbol_name": "def login"},
        )
        source = SimpleNamespace(
            id="source-1",
            index_mode=SourceIndexMode.strict,
            source_type=SourceType.google_drive,
            connection_config={"file_id": "x", "file_path": "app/auth.py"},
            snapshot_id="a" * 40,
            last_commit_sha="a" * 40,
            connected_account_id="account-1",
            index_health={"policy": {"allow_code_snippets": True}},
        )
        db = MagicMock()
        result = MagicMock()
        result.fetchall.return_value = [SimpleNamespace(Chunk=chunk_row, Source=source)]
        db.execute = AsyncMock(return_value=result)

        with patch(
            "app.domains.retrieval.hydration._load_canonical_source_text",
            AsyncMock(return_value="def login():\n    return True\n"),
        ):
            hydrated = await hydrate_retrieved_chunks(
                [{"chunk_id": chunk_id, "content": "stale", "chunk_type": "code_snippet"}],
                db,
            )

        assert hydrated[0]["content"] == "stale"

    @pytest.mark.asyncio
    async def test_hydrates_strict_documentation_chunk_when_hash_matches(self):
        chunk_id = "8f2d291f-48e6-4936-bdfc-99c1cb0b7df9"
        hydrated_text = "Authentication\n\nJWT tokens guard protected routes."
        chunk_row = SimpleNamespace(
            id=chunk_id,
            chunk_type=ChunkType.documentation,
            start_line=4,
            end_line=4,
            source_ref="README.md",
            snapshot_id="hash:abcd1234",
            segment_id="README.md:4-4:documentation",
            content_hash=hash_text(hydrated_text),
            lineage=ChunkLineage.file_backed,
            chunk_metadata={"heading": "Authentication"},
        )
        source = SimpleNamespace(
            id="source-2",
            index_mode=SourceIndexMode.strict,
            source_type=SourceType.markdown,
            connection_config={"content": "# README\n\n## Authentication\nJWT tokens guard protected routes.\n"},
            snapshot_id="hash:abcd1234",
            last_commit_sha=None,
            connected_account_id=None,
            index_health={"policy": {"allow_code_snippets": False}},
        )
        db = MagicMock()
        result = MagicMock()
        result.fetchall.return_value = [SimpleNamespace(Chunk=chunk_row, Source=source)]
        db.execute = AsyncMock(return_value=result)

        with patch(
            "app.domains.retrieval.hydration._build_canonical_chunk_map",
            return_value={
                ("documentation", "README.md:4-4:documentation"): {
                    "content": hydrated_text,
                    "chunk_type": ChunkType.documentation,
                    "segment_id": "README.md:4-4:documentation",
                }
            },
        ):
            hydrated = await hydrate_retrieved_chunks(
                [{"chunk_id": chunk_id, "content": "stale", "chunk_type": "documentation"}],
                db,
            )

        assert hydrated[0]["content"] == hydrated_text
        assert hydrated[0]["hydrated"] is True
