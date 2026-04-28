"""
Unit tests for app.domains.memory.service — run_memory_extraction orchestration.

Uses AsyncMock for DB + Redis. Verifies idempotency, lock behaviour,
failure handling, and stats output. No real DB, no real Redis, no LLM calls.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domains.graph.extractor import GraphExtractionResult
from app.domains.memory.evidence import MemoryEvidenceBundle
from app.domains.memory.service import (
    clear_memory_chunks_for_twin,
    get_memory_brief,
    run_memory_extraction,
)

doctwin_ID = "00000000-0000-0000-0000-000000000042"


def _make_db_session(memory_brief_text: str | None = None):
    """Create a minimal mock AsyncSession."""
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.add = MagicMock()

    mock_config = MagicMock()
    mock_config.doctwin_id = uuid.UUID(doctwin_ID)
    mock_config.memory_brief = memory_brief_text
    mock_config.memory_brief_status = None
    mock_config.memory_brief_generated_at = None

    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none = MagicMock(return_value=mock_config)
    db.execute.return_value = scalar_result

    return db, mock_config


def _evidence_bundle() -> MemoryEvidenceBundle:
    return MemoryEvidenceBundle(
        doctwin_id=doctwin_ID,
        workspace_id="00000000-0000-0000-0000-000000000099",
        structure_overview=[],
    )


def _patch_generate_brief(brief_text: str = "# Brief\n\nSome content."):
    return {"generate_memory_brief": AsyncMock(return_value=brief_text)}


def _patch_memory_evidence():
    return {
        "load_doctwin_memory_evidence": AsyncMock(return_value=_evidence_bundle()),
        "_rebuild_workspace_synthesis_for_twin": AsyncMock(return_value=True),
    }


def _make_redis(acquired=True):
    redis = MagicMock()
    redis.set = AsyncMock(return_value=acquired)
    redis.delete = AsyncMock()
    return redis


def _patch_graph_layers():
    empty_graph = GraphExtractionResult()
    return {
        "build_deterministic_graph": AsyncMock(return_value=empty_graph),
        "extract_graph_from_chunks": AsyncMock(return_value=empty_graph),
        "merge_graph_extractions": MagicMock(return_value=empty_graph),
        "rebuild_graph": AsyncMock(),
        "get_graph_summary": AsyncMock(return_value=""),
    }


def _service_patch_kwargs(
    *,
    redis,
    graph,
    brief_mocks,
    mem,
    embed_side_effect=None,
    embed_return=None,
    load_doctwin_chunks=None,
    build_structure_overview=None,
    clear_memory_chunks=0,
    set_brief_status=None,
    save_memory_brief=None,
):
    embed_mock = AsyncMock(
        side_effect=embed_side_effect if embed_side_effect is not None else None,
        return_value=embed_return if embed_side_effect is None else None,
    )
    return {
        "get_redis": MagicMock(return_value=redis),
        "_load_doctwin_chunks": load_doctwin_chunks if load_doctwin_chunks is not None else AsyncMock(return_value=[]),
        "_build_structure_overview": (
            build_structure_overview if build_structure_overview is not None else AsyncMock(return_value=[])
        ),
        "clear_memory_chunks_for_twin": AsyncMock(return_value=clear_memory_chunks),
        "load_doctwin_memory_evidence": mem["load_doctwin_memory_evidence"],
        "build_deterministic_graph": graph["build_deterministic_graph"],
        "extract_graph_from_chunks": graph["extract_graph_from_chunks"],
        "merge_graph_extractions": graph["merge_graph_extractions"],
        "rebuild_graph": graph["rebuild_graph"],
        "get_graph_summary": graph["get_graph_summary"],
        "generate_memory_brief": brief_mocks["generate_memory_brief"],
        "_rebuild_workspace_synthesis_for_twin": mem["_rebuild_workspace_synthesis_for_twin"],
        "_embed_and_write_chunks": embed_mock,
        "_set_brief_status": set_brief_status if set_brief_status is not None else AsyncMock(),
        "_save_memory_brief": save_memory_brief if save_memory_brief is not None else AsyncMock(),
    }


class TestRedisLock:
    @pytest.mark.asyncio
    async def test_returns_skipped_when_lock_not_acquired(self):
        db, _ = _make_db_session()
        redis = _make_redis(acquired=False)

        with patch("app.domains.memory.service.get_redis", return_value=redis):
            stats = await run_memory_extraction(doctwin_ID, db)

        assert stats["status"] == "skipped"
        assert stats["reason"] == "extraction already in progress"

    @pytest.mark.asyncio
    async def test_lock_is_always_released(self):
        db, _ = _make_db_session()
        redis = _make_redis(acquired=True)

        with (
            patch("app.domains.memory.service.get_redis", return_value=redis),
            patch("app.domains.memory.service._load_doctwin_chunks", AsyncMock(side_effect=RuntimeError("unexpected"))),
            patch("app.domains.memory.service._set_brief_status", AsyncMock()),
        ):
            stats = await run_memory_extraction(doctwin_ID, db)

        redis.delete.assert_called_once()
        assert stats["status"] == "failed"


class TestRunMemoryExtractionStats:
    @pytest.mark.asyncio
    async def test_successful_extraction_returns_ready_stats(self):
        db, _ = _make_db_session()
        redis = _make_redis(acquired=True)
        brief_mocks = _patch_generate_brief()
        graph = _patch_graph_layers()
        mem = _patch_memory_evidence()

        with patch.multiple(
            "app.domains.memory.service",
            **_service_patch_kwargs(
                redis=redis,
                graph=graph,
                brief_mocks=brief_mocks,
                mem=mem,
                embed_side_effect=lambda chunks, *a, **kw: [MagicMock()] * len(chunks),
            ),
        ):
            stats = await run_memory_extraction(doctwin_ID, db)

        assert stats["status"] == "ready"
        assert stats["brief_generated"] is True
        assert stats["workspace_synthesis_generated"] is True
        assert stats["error"] is None
        brief_mocks["generate_memory_brief"].assert_called_once()

    @pytest.mark.asyncio
    async def test_commit_history_does_not_change_pipeline(self):
        """commit_history is logged only; extraction uses graph + brief."""
        db, _ = _make_db_session()
        redis = _make_redis(acquired=True)
        brief_mocks = _patch_generate_brief()
        graph = _patch_graph_layers()
        mem = _patch_memory_evidence()
        commits = [
            {
                "sha": "abc",
                "message": "test commit",
                "author_name": "Dev",
                "author_date": "2026-04-14",
                "files_changed": [],
                "additions": 0,
                "deletions": 0,
            }
        ]

        with patch.multiple(
            "app.domains.memory.service",
            **_service_patch_kwargs(
                redis=redis,
                graph=graph,
                brief_mocks=brief_mocks,
                mem=mem,
                embed_side_effect=lambda chunks, *a, **kw: [MagicMock()] * len(chunks),
            ),
        ):
            stats = await run_memory_extraction(doctwin_ID, db, commit_history=commits)

        assert stats["status"] == "ready"
        assert stats["brief_generated"] is True

    @pytest.mark.asyncio
    async def test_failed_when_brief_generation_returns_empty(self):
        db, _ = _make_db_session()
        redis = _make_redis(acquired=True)
        brief_mocks = _patch_generate_brief(brief_text="")
        graph = _patch_graph_layers()
        mem = _patch_memory_evidence()

        with patch.multiple(
            "app.domains.memory.service",
            **_service_patch_kwargs(
                redis=redis,
                graph=graph,
                brief_mocks=brief_mocks,
                mem=mem,
                embed_return=[],
            ),
        ):
            stats = await run_memory_extraction(doctwin_ID, db)

        assert stats["status"] == "failed"
        assert stats["brief_generated"] is False


class TestNeverRaises:
    @pytest.mark.asyncio
    async def test_brief_generation_exception_does_not_propagate(self):
        db, _ = _make_db_session()
        redis = _make_redis(acquired=True)
        graph = _patch_graph_layers()
        mem = _patch_memory_evidence()
        brief_mocks = {"generate_memory_brief": AsyncMock(side_effect=RuntimeError("LLM exploded"))}

        with patch.multiple(
            "app.domains.memory.service",
            **_service_patch_kwargs(
                redis=redis,
                graph=graph,
                brief_mocks=brief_mocks,
                mem=mem,
                set_brief_status=AsyncMock(),
            ),
        ):
            stats = await run_memory_extraction(doctwin_ID, db)

        assert stats["status"] == "failed"
        assert "LLM exploded" in stats["error"]
        redis.delete.assert_called_once()


class TestClearMemoryChunks:
    @pytest.mark.asyncio
    async def test_returns_deleted_count(self):
        db = MagicMock()

        mock_result = MagicMock()
        mock_result.fetchall = MagicMock(return_value=[MagicMock(), MagicMock(), MagicMock()])
        db.execute = AsyncMock(return_value=mock_result)

        count = await clear_memory_chunks_for_twin(doctwin_ID, db)
        assert count == 3

    @pytest.mark.asyncio
    async def test_returns_zero_when_nothing_to_delete(self):
        db = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall = MagicMock(return_value=[])
        db.execute = AsyncMock(return_value=mock_result)

        count = await clear_memory_chunks_for_twin(doctwin_ID, db)
        assert count == 0


class TestGetMemoryBrief:
    @pytest.mark.asyncio
    async def test_returns_brief_when_present(self):
        db = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value="# Brief content")
        db.execute = AsyncMock(return_value=mock_result)

        result = await get_memory_brief(doctwin_ID, db)
        assert result == "# Brief content"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_generated(self):
        db = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=mock_result)

        result = await get_memory_brief(doctwin_ID, db)
        assert result is None
