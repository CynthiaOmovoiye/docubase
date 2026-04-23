import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domains.chat.service import _HEDGE_RE
from app.domains.retrieval.router import (
    _resolve_refs_from_inventory,
    _route_by_structure,
)


class TestHedgePattern:
    def test_matches_known_hedging_phrases(self):
        assert _HEDGE_RE.search("I don't have specific information about Week 3.")
        assert _HEDGE_RE.search("No information about the finale is available.")

    def test_does_not_match_confident_answer(self):
        assert not _HEDGE_RE.search("Week 3 covers AWS Lambda deployment and ECS.")


class TestResolveRefsFromInventory:
    def test_normalises_week_spacing(self):
        inventory = {
            "meaningful_dirs": {
                "week3": ["week3/README.md"],
                "guides": ["guides/setup.md"],
            }
        }

        assert _resolve_refs_from_inventory(["week 3"], inventory) == ["week3"]

    def test_resolves_nested_directory(self):
        inventory = {
            "meaningful_dirs": {
                "app/api": ["app/api/routes.py"],
                "_root": ["README.md"],
            }
        }

        assert _resolve_refs_from_inventory(["app/api"], inventory) == ["app/api"]

    def test_falls_back_to_exact_file_match(self):
        inventory = {
            "meaningful_dirs": {
                "scripts": ["scripts/deploy.sh"],
            }
        }

        assert _resolve_refs_from_inventory(["scripts/deploy.sh"], inventory) == ["scripts/deploy.sh"]


class TestRouteByStructure:
    @pytest.mark.asyncio
    async def test_returns_doctwin_when_only_one_matches(self):
        db = MagicMock()
        doctwin_id = uuid.uuid4()
        result = MagicMock()
        result.fetchall.return_value = [
            SimpleNamespace(
                doctwin_id=doctwin_id,
                structure_index={"meaningful_dirs": {"week3": ["week3/README.md"]}},
            ),
            SimpleNamespace(
                doctwin_id=uuid.uuid4(),
                structure_index={"meaningful_dirs": {"app/api": ["app/api/routes.py"]}},
            ),
        ]
        db.execute = AsyncMock(return_value=result)

        routed = await _route_by_structure(str(uuid.uuid4()), ["week 3"], db)

        assert routed == str(doctwin_id)

    @pytest.mark.asyncio
    async def test_returns_none_when_ambiguous(self):
        db = MagicMock()
        result = MagicMock()
        result.fetchall.return_value = [
            SimpleNamespace(
                doctwin_id=uuid.uuid4(),
                structure_index={"meaningful_dirs": {"week3": ["week3/README.md"]}},
            ),
            SimpleNamespace(
                doctwin_id=uuid.uuid4(),
                structure_index={"meaningful_dirs": {"week3": ["week3/overview.md"]}},
            ),
        ]
        db.execute = AsyncMock(return_value=result)

        routed = await _route_by_structure(str(uuid.uuid4()), ["week3"], db)

        assert routed is None
