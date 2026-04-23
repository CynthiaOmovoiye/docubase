from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domains.sources.service import (
    _is_backfill_candidate,
    list_sources,
    list_legacy_backfill_candidates,
    mark_sources_pending_for_backfill,
)
from app.models.source import SourceIndexMode, SourceStatus


class TestBackfillCandidateSelection:
    def test_accepts_legacy_ready_failed_and_needs_resync_sources(self):
        for status in (
            SourceStatus.ready,
            SourceStatus.failed,
            SourceStatus.needs_resync,
        ):
            source = SimpleNamespace(index_mode=SourceIndexMode.legacy, status=status)
            assert _is_backfill_candidate(source) is True

    def test_rejects_strict_and_active_processing_sources(self):
        assert _is_backfill_candidate(
            SimpleNamespace(index_mode=SourceIndexMode.strict, status=SourceStatus.ready)
        ) is False
        assert _is_backfill_candidate(
            SimpleNamespace(index_mode=SourceIndexMode.legacy, status=SourceStatus.pending)
        ) is False
        assert _is_backfill_candidate(
            SimpleNamespace(index_mode=SourceIndexMode.legacy, status=SourceStatus.processing)
        ) is False


class TestListLegacyBackfillCandidates:
    @pytest.mark.asyncio
    async def test_filters_sources_after_ownership_check(self):
        db = MagicMock()
        legacy = SimpleNamespace(index_mode=SourceIndexMode.legacy, status=SourceStatus.ready)
        strict = SimpleNamespace(index_mode=SourceIndexMode.strict, status=SourceStatus.ready)
        pending = SimpleNamespace(index_mode=SourceIndexMode.legacy, status=SourceStatus.pending)
        result = MagicMock()
        result.scalars.return_value.all.return_value = [legacy, strict, pending]
        db.execute = AsyncMock(return_value=result)

        with patch(
            "app.domains.sources.service.assert_twin_owned_by",
            AsyncMock(return_value=SimpleNamespace()),
        ) as assert_owned:
            candidates = await list_legacy_backfill_candidates(
                twin_id="00000000-0000-0000-0000-000000000001",
                user_id="00000000-0000-0000-0000-000000000002",
                db=db,
            )

        assert_owned.assert_awaited_once()
        assert candidates == [legacy]


class TestListSources:
    @pytest.mark.asyncio
    async def test_hides_internal_memory_sources(self):
        db = MagicMock()
        external = SimpleNamespace(name="repo")
        internal = SimpleNamespace(name="__memory__")
        result = MagicMock()
        result.scalars.return_value.all.return_value = [external]
        db.execute = AsyncMock(return_value=result)

        with patch(
            "app.domains.sources.service.assert_twin_owned_by",
            AsyncMock(return_value=SimpleNamespace()),
        ):
            sources = await list_sources(
                twin_id="00000000-0000-0000-0000-000000000001",
                user_id="00000000-0000-0000-0000-000000000002",
                db=db,
            )

        assert sources == [external]


class TestMarkSourcesPendingForBackfill:
    @pytest.mark.asyncio
    async def test_marks_existing_sources_pending_and_clears_errors(self):
        db = MagicMock()
        db.flush = AsyncMock()
        source_a = SimpleNamespace(status=SourceStatus.failed, last_error="boom")
        source_b = SimpleNamespace(status=SourceStatus.ready, last_error=None)
        missing = None
        db.execute = AsyncMock(side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=source_a)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=source_b)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=missing)),
        ])

        updated = await mark_sources_pending_for_backfill(
            [
                "00000000-0000-0000-0000-000000000011",
                "00000000-0000-0000-0000-000000000012",
                "00000000-0000-0000-0000-000000000013",
            ],
            db,
        )

        assert updated == 2
        assert source_a.status == SourceStatus.pending
        assert source_a.last_error is None
        assert source_b.status == SourceStatus.pending
        assert source_b.last_error is None
        db.flush.assert_awaited_once()
