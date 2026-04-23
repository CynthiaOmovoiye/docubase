import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domains.embedding.embedder import EmbeddingProfile
from app.domains.sources.service import (
    mark_processing_sources_failed,
    mark_processing_sources_ready,
)
from app.jobs.ingestion import (
    _finalise_noop_full_sync,
    _incoming_root_hash,
    _profiles_for_source_sync,
    _should_short_circuit_full_sync,
)
from app.models.source import SourceIndexMode, SourceStatus, SourceType


class TestProfilesForSourceSync:
    def test_delta_sync_keeps_existing_profile_sticky(self):
        source = SimpleNamespace(
            embedding_provider="jina",
            embedding_model="jina-embeddings-v3",
            embedding_dimensions=1024,
        )

        profiles = _profiles_for_source_sync(source, is_full_sync=False)

        assert profiles == [EmbeddingProfile("jina", "jina-embeddings-v3", 1024)]

    def test_full_sync_uses_primary_then_fallback(self):
        source = SimpleNamespace(
            embedding_provider="jina",
            embedding_model="jina-embeddings-v3",
            embedding_dimensions=1024,
        )
        primary = EmbeddingProfile("jina", "jina-embeddings-v3", 1024)
        fallback = EmbeddingProfile("voyage", "voyage-3.5-lite", 1024)

        with (
            patch("app.jobs.ingestion.get_primary_embedding_profile", return_value=primary),
            patch("app.jobs.ingestion.get_fallback_embedding_profile", return_value=fallback),
        ):
            profiles = _profiles_for_source_sync(source, is_full_sync=True)

        assert profiles == [primary, fallback]


class TestContentAddressedNoopSync:
    def test_incoming_root_hash_is_deterministic(self):
        result_a = SimpleNamespace(
            files=[
                SimpleNamespace(path="b.py", content="print('b')"),
                SimpleNamespace(path="a.py", content="print('a')"),
            ]
        )
        result_b = SimpleNamespace(
            files=[
                SimpleNamespace(path="a.py", content="print('a')"),
                SimpleNamespace(path="b.py", content="print('b')"),
            ]
        )

        assert _incoming_root_hash(result_a) == _incoming_root_hash(result_b)

    def test_short_circuit_only_for_strict_full_sync_with_same_policy_and_hash(self):
        source = SimpleNamespace(
            index_mode=SourceIndexMode.strict,
            snapshot_id="snap",
            snapshot_root_hash="same",
            structure_index={"total_files": 2},
            index_health={
                "policy": {"allow_code_snippets": False},
                "implementation_index": {"ready": True, "schema_version": 2, "fact_schema_version": 4},
                "canonical_mirror": {
                    "ready": True,
                    "snapshot_id": "snap",
                    "snapshot_root_hash": "same",
                    "file_count": 2,
                },
            },
        )
        result = SimpleNamespace(is_full_sync=True)

        assert _should_short_circuit_full_sync(
            source=source,
            connector_result=result,
            incoming_root_hash="same",
            allow_code_snippets=False,
        )
        assert not _should_short_circuit_full_sync(
            source=source,
            connector_result=result,
            incoming_root_hash="same",
            allow_code_snippets=True,
        )
        assert not _should_short_circuit_full_sync(
            source=SimpleNamespace(
                index_mode=SourceIndexMode.legacy,
                snapshot_id="snap",
                snapshot_root_hash="same",
                structure_index={"total_files": 2},
                index_health={
                    "policy": {"allow_code_snippets": False},
                    "implementation_index": {"ready": True, "schema_version": 2, "fact_schema_version": 4},
                    "canonical_mirror": {
                        "ready": True,
                        "snapshot_id": "snap",
                        "snapshot_root_hash": "same",
                        "file_count": 2,
                    },
                },
            ),
            connector_result=result,
            incoming_root_hash="same",
            allow_code_snippets=False,
        )
        assert not _should_short_circuit_full_sync(
            source=SimpleNamespace(
                index_mode=SourceIndexMode.strict,
                snapshot_id="snap",
                snapshot_root_hash="same",
                structure_index={"total_files": 2},
                index_health={"policy": {"allow_code_snippets": False}},
            ),
            connector_result=result,
            incoming_root_hash="same",
            allow_code_snippets=False,
        )

        assert not _should_short_circuit_full_sync(
            source=SimpleNamespace(
                index_mode=SourceIndexMode.strict,
                snapshot_id="snap",
                snapshot_root_hash="same",
                structure_index={"total_files": 2},
                index_health={
                    "policy": {"allow_code_snippets": False},
                    "implementation_index": {"ready": True, "schema_version": 2, "fact_schema_version": 4},
                },
            ),
            connector_result=result,
            incoming_root_hash="same",
            allow_code_snippets=False,
        )

        assert not _should_short_circuit_full_sync(
            source=SimpleNamespace(
                index_mode=SourceIndexMode.strict,
                snapshot_id="snap",
                snapshot_root_hash="same",
                structure_index={"total_files": 2},
                index_health={
                    "policy": {"allow_code_snippets": False},
                    "implementation_index": {"ready": True, "schema_version": 2},
                    "canonical_mirror": {
                        "ready": True,
                        "snapshot_id": "snap",
                        "snapshot_root_hash": "same",
                        "file_count": 2,
                    },
                },
            ),
            connector_result=result,
            incoming_root_hash="same",
            allow_code_snippets=False,
        )

    @pytest.mark.asyncio
    async def test_finalise_noop_sync_updates_source_and_chunk_snapshot(self):
        source = SimpleNamespace(
            id=uuid.uuid4(),
            source_type=SourceType.github_repo,
            snapshot_id="old",
            snapshot_root_hash="oldhash",
            last_commit_sha="old",
            last_page_token=None,
            index_health={
                "coverage": {},
                "policy": {"allow_code_snippets": False},
                "implementation_index": {"ready": True, "schema_version": 2},
            },
            status=SourceStatus.ingesting,
            last_error="stale",
        )
        result = SimpleNamespace(
            fetch_metadata={},
            head_sha="a" * 40,
            next_page_token=None,
            files=[SimpleNamespace(path="app.py", content="print('x')")],
        )
        db = MagicMock()
        db.execute = AsyncMock()
        db.flush = AsyncMock()

        await _finalise_noop_full_sync(
            source=source,
            connector_result=result,
            incoming_root_hash="newhash",
            db=db,
        )

        assert source.status == SourceStatus.ready
        assert source.last_error is None
        assert source.snapshot_id == "a" * 40
        assert source.snapshot_root_hash == "newhash"
        assert source.index_health["coverage"]["files_received"] == 1
        assert source.index_health["coverage"]["files_processed"] == 0
        db.execute.assert_awaited()


class TestProcessingSourceFinalisation:
    @pytest.mark.asyncio
    async def test_mark_processing_sources_ready_promotes_sources(self):
        db = MagicMock()
        db.flush = AsyncMock()
        source = SimpleNamespace(status=SourceStatus.processing, last_error="old", name="repo")
        result = MagicMock()
        result.scalars.return_value.all.return_value = [source]
        db.execute = AsyncMock(return_value=result)

        count = await mark_processing_sources_ready(str(uuid.uuid4()), db)

        assert count == 1
        assert source.status == SourceStatus.ready
        assert source.last_error is None

    @pytest.mark.asyncio
    async def test_mark_processing_sources_failed_sets_error(self):
        db = MagicMock()
        db.flush = AsyncMock()
        source = SimpleNamespace(status=SourceStatus.processing, last_error=None, name="repo")
        result = MagicMock()
        result.scalars.return_value.all.return_value = [source]
        db.execute = AsyncMock(return_value=result)

        count = await mark_processing_sources_failed(str(uuid.uuid4()), "memory failed", db)

        assert count == 1
        assert source.status == SourceStatus.failed
        assert source.last_error == "memory failed"
