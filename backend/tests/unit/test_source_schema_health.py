from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.models.source import SourceIndexMode, SourceStatus, SourceType
from app.schemas.sources import SourceResponse


def _source(*, freshness: dict | None, status: SourceStatus = SourceStatus.ready):
    now = datetime.now(UTC)
    return SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        doctwin_id="22222222-2222-2222-2222-222222222222",
        name="Product docs",
        source_type=SourceType.google_drive,
        status=status,
        last_error=None,
        snapshot_id="sha:test",
        snapshot_root_hash="abc",
        index_mode=SourceIndexMode.strict,
        index_health={
            "freshness": freshness or {},
            "implementation_index": {
                "parser_coverage_ratio": 0.75,
                "files_indexed": 4,
                "symbols_indexed": 10,
                "relationships_indexed": 7,
            },
        },
        created_at=now,
        updated_at=now,
        connection_config={"file_id": "abc123", "file_path": "docs/README.md"},
    )


def test_source_response_marks_fresh_index_as_fresh():
    source = _source(
        freshness={
            "last_indexed_at": datetime.now(UTC).isoformat(),
            "stale_after_hours": 24,
        }
    )

    response = SourceResponse.from_source(source)

    assert response.index_health["freshness"]["is_stale"] is False
    assert response.index_health["freshness"]["label"] == "Fresh"
    assert response.index_health["implementation_index"]["parser_coverage_percent"] == 75.0


def test_source_response_marks_old_index_as_stale():
    source = _source(
        freshness={
            "last_indexed_at": (datetime.now(UTC) - timedelta(hours=30)).isoformat(),
            "stale_after_hours": 24,
        }
    )

    response = SourceResponse.from_source(source)

    assert response.index_health["freshness"]["is_stale"] is True
    assert response.index_health["freshness"]["label"] == "Stale"


def test_source_response_marks_failed_source_as_stale():
    source = _source(
        freshness={},
        status=SourceStatus.failed,
    )
    source.last_error = "sync failed"

    response = SourceResponse.from_source(source)

    assert response.index_health["freshness"]["is_stale"] is True
    assert response.index_health["freshness"]["reason"] == "sync failed"
