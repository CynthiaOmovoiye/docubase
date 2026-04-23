"""
Unit tests for app.domains.memory.service — run_memory_extraction orchestration.

Uses AsyncMock for DB + Redis. Verifies idempotency, lock behaviour,
failure handling, and stats output. No real DB, no real Redis, no LLM calls.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domains.graph.extractor import GraphExtractionResult
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

    # TwinConfig mock row
    mock_config = MagicMock()
    mock_config.doctwin_id = uuid.UUID(doctwin_ID)
    mock_config.memory_brief = memory_brief_text
    mock_config.memory_brief_status = None
    mock_config.memory_brief_generated_at = None

    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none = MagicMock(return_value=mock_config)
    db.execute.return_value = scalar_result

    return db, mock_config


def _patch_extractors(
    arch_chunks=None,
    risk_chunks=None,
    change_chunks=None,
    brief_text="# Brief\n\nSome content.",
):
    """Patch all four extractor functions with controllable return values."""
    arch_chunks = arch_chunks or [
        {
            "chunk_type": "architecture_summary",
            "content": "FastAPI backend",
            "source_ref": f"__memory__/{doctwin_ID}",
            "chunk_metadata": {},
        }
    ]
    risk_chunks = risk_chunks or [
        {
            "chunk_type": "risk_note",
            "content": "High risk: no error handling",
            "source_ref": f"__memory__/{doctwin_ID}",
            "chunk_metadata": {"severity": "high"},
        }
    ]
    change_chunks = change_chunks or []

    patches = {
        "extract_architecture_chunks": AsyncMock(return_value=arch_chunks),
        "extract_change_entry_chunks": AsyncMock(return_value=change_chunks),
        "generate_memory_brief": AsyncMock(return_value=brief_text),
    }
    return patches


def _make_memory_bundle():
    return SimpleNamespace(
        doctwin_id=doctwin_ID,
        workspace_id="00000000-0000-0000-0000-000000000099",
        indexed_files=[],
        indexed_symbols=[],
        indexed_relationships=[],
        git_activities=[],
        structure_overview=[],
    )


def _patch_memory_evidence(
    *,
    feature_chunks=None,
    auth_chunks=None,
    onboarding_chunks=None,
    risk_chunks=None,
    change_chunks=None,
):
    feature_chunks = feature_chunks or [
        {
            "chunk_type": "feature_summary",
            "content": "Feature summary",
            "source_ref": f"__memory__/{doctwin_ID}",
            "chunk_metadata": {"provenance": []},
        }
    ]
    auth_chunks = auth_chunks or [
        {
            "chunk_type": "auth_flow",
            "content": "Auth flow",
            "source_ref": f"__memory__/{doctwin_ID}",
            "chunk_metadata": {"provenance": []},
        }
    ]
    onboarding_chunks = onboarding_chunks or [
        {
            "chunk_type": "onboarding_map",
            "content": "Onboarding map",
            "source_ref": f"__memory__/{doctwin_ID}",
            "chunk_metadata": {"provenance": []},
        }
    ]
    risk_chunks = risk_chunks or [
        {
            "chunk_type": "risk_note",
            "content": "High risk: no error handling",
            "source_ref": f"__memory__/{doctwin_ID}",
            "chunk_metadata": {"severity": "high", "provenance": []},
        }
    ]
    change_chunks = change_chunks or []
    return {
        "load_doctwin_memory_evidence": AsyncMock(return_value=_make_memory_bundle()),
        "build_feature_summary_chunks": MagicMock(return_value=feature_chunks),
        "build_auth_flow_chunks": MagicMock(return_value=auth_chunks),
        "build_onboarding_map_chunks": MagicMock(return_value=onboarding_chunks),
        "build_risk_summary_chunks": MagicMock(return_value=risk_chunks),
        "build_change_summary_chunks": MagicMock(return_value=change_chunks),
        "_rebuild_workspace_synthesis_for_twin": AsyncMock(return_value=True),
    }


def _make_redis(acquired=True):
    """Mock Redis client that returns `acquired` for SET NX."""
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
    ext,
    mem,
    embed_side_effect=None,
    embed_return=None,
    load_doctwin_chunks=None,
    build_structure_overview=None,
    clear_memory_chunks=0,
    extract_architecture_chunks=None,
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
        "extract_architecture_chunks": (
            extract_architecture_chunks
            if extract_architecture_chunks is not None
            else ext["extract_architecture_chunks"]
        ),
        "build_feature_summary_chunks": mem["build_feature_summary_chunks"],
        "build_auth_flow_chunks": mem["build_auth_flow_chunks"],
        "build_onboarding_map_chunks": mem["build_onboarding_map_chunks"],
        "build_risk_summary_chunks": mem["build_risk_summary_chunks"],
        "build_change_summary_chunks": mem["build_change_summary_chunks"],
        "extract_change_entry_chunks": ext["extract_change_entry_chunks"],
        "generate_memory_brief": ext["generate_memory_brief"],
        "_rebuild_workspace_synthesis_for_twin": mem["_rebuild_workspace_synthesis_for_twin"],
        "_embed_and_write_chunks": embed_mock,
        "_set_brief_status": set_brief_status if set_brief_status is not None else AsyncMock(),
        "_save_memory_brief": save_memory_brief if save_memory_brief is not None else AsyncMock(),
    }


# ── Lock behaviour ────────────────────────────────────────────────────────────

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
        """Lock must be released even when extraction raises an unexpected error."""
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


# ── Stats output ──────────────────────────────────────────────────────────────

class TestRunMemoryExtractionStats:
    @pytest.mark.asyncio
    async def test_successful_extraction_returns_ready_stats(self):
        db, _ = _make_db_session()
        redis = _make_redis(acquired=True)
        ext = _patch_extractors()
        graph = _patch_graph_layers()
        mem = _patch_memory_evidence()

        with patch.multiple(
            "app.domains.memory.service",
            **_service_patch_kwargs(
                redis=redis,
                graph=graph,
                ext=ext,
                mem=mem,
                embed_side_effect=lambda chunks, *a, **kw: [MagicMock()] * len(chunks),
            ),
        ):
            stats = await run_memory_extraction(doctwin_ID, db)

        assert stats["status"] == "ready"
        assert stats["arch_chunks"] == 1
        assert stats["feature_chunks"] == 1
        assert stats["auth_chunks"] == 1
        assert stats["onboarding_chunks"] == 1
        assert stats["risk_chunks"] == 1
        assert stats["brief_generated"] is True
        assert stats["workspace_synthesis_generated"] is True
        assert stats["error"] is None

    @pytest.mark.asyncio
    async def test_change_chunks_counted_when_commit_history_provided(self):
        db, _ = _make_db_session()
        redis = _make_redis(acquired=True)
        change_chunks = [
            {
                "chunk_type": "change_entry",
                "content": "Week of April 14: added memory",
                "source_ref": f"__memory__/{doctwin_ID}",
                "chunk_metadata": {},
            }
        ]
        ext = _patch_extractors(change_chunks=change_chunks)
        graph = _patch_graph_layers()
        mem = _patch_memory_evidence(change_chunks=change_chunks)
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
                ext=ext,
                mem=mem,
                embed_side_effect=lambda chunks, *a, **kw: [MagicMock()] * len(chunks),
            ),
        ):
            stats = await run_memory_extraction(doctwin_ID, db, commit_history=commits)

        assert stats["change_chunks"] == 1

    @pytest.mark.asyncio
    async def test_no_commit_history_skips_change_extraction(self):
        db, _ = _make_db_session()
        redis = _make_redis(acquired=True)
        ext = _patch_extractors()
        graph = _patch_graph_layers()
        mem = _patch_memory_evidence(change_chunks=[])

        with patch.multiple(
            "app.domains.memory.service",
            **_service_patch_kwargs(
                redis=redis,
                graph=graph,
                ext=ext,
                mem=mem,
                embed_side_effect=lambda chunks, *a, **kw: [MagicMock()] * len(chunks),
            ),
        ):
            stats = await run_memory_extraction(doctwin_ID, db, commit_history=None)

        ext["extract_change_entry_chunks"].assert_not_called()
        assert stats["change_chunks"] == 0

    @pytest.mark.asyncio
    async def test_failed_when_brief_generation_returns_empty(self):
        db, _ = _make_db_session()
        redis = _make_redis(acquired=True)
        ext = _patch_extractors(brief_text="")
        graph = _patch_graph_layers()
        mem = _patch_memory_evidence()

        with patch.multiple(
            "app.domains.memory.service",
            **_service_patch_kwargs(
                redis=redis,
                graph=graph,
                ext=ext,
                mem=mem,
                embed_return=[],
            ),
        ):
            stats = await run_memory_extraction(doctwin_ID, db)

        assert stats["status"] == "failed"
        assert stats["brief_generated"] is False


# ── Never raises ──────────────────────────────────────────────────────────────

class TestNeverRaises:
    @pytest.mark.asyncio
    async def test_extractor_exception_does_not_propagate(self):
        """run_memory_extraction must never raise — all errors are caught."""
        db, _ = _make_db_session()
        redis = _make_redis(acquired=True)
        graph = _patch_graph_layers()
        mem = _patch_memory_evidence()

        with patch.multiple(
            "app.domains.memory.service",
            **_service_patch_kwargs(
                redis=redis,
                graph=graph,
                ext=_patch_extractors(),
                mem=mem,
                extract_architecture_chunks=AsyncMock(side_effect=RuntimeError("LLM exploded")),
                set_brief_status=AsyncMock(),
            ),
        ):
            # Must not raise
            stats = await run_memory_extraction(doctwin_ID, db)

        assert stats["status"] == "failed"
        assert "LLM exploded" in stats["error"]
        # Lock must still have been released
        redis.delete.assert_called_once()


# ── clear_memory_chunks_for_twin ──────────────────────────────────────────────

class TestClearMemoryChunks:
    @pytest.mark.asyncio
    async def test_returns_deleted_count(self):
        db = MagicMock()

        # Simulate 3 rows returned by RETURNING id
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


# ── get_memory_brief ──────────────────────────────────────────────────────────

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
