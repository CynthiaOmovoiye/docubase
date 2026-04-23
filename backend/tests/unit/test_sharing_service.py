import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domains.sharing.service import ForbiddenError, list_surfaces_for_workspace


class TestListSurfacesForWorkspace:
    @pytest.mark.asyncio
    async def test_returns_active_workspace_surfaces_for_owner(self):
        workspace_id = uuid.uuid4()
        user_id = uuid.uuid4()
        db = MagicMock()

        workspace_result = MagicMock()
        workspace_result.scalar_one_or_none.return_value = SimpleNamespace(
            id=workspace_id,
            owner_id=user_id,
        )

        surfaces = [
            SimpleNamespace(id=uuid.uuid4(), public_slug="workspace-1"),
            SimpleNamespace(id=uuid.uuid4(), public_slug="workspace-2"),
        ]
        surfaces_result = MagicMock()
        surfaces_result.scalars.return_value.all.return_value = surfaces

        db.execute = AsyncMock(side_effect=[workspace_result, surfaces_result])

        result = await list_surfaces_for_workspace(workspace_id, user_id, db)

        assert result == surfaces
        assert db.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_raises_forbidden_for_non_owner(self):
        workspace_id = uuid.uuid4()
        owner_id = uuid.uuid4()
        other_user_id = uuid.uuid4()
        db = MagicMock()

        workspace_result = MagicMock()
        workspace_result.scalar_one_or_none.return_value = SimpleNamespace(
            id=workspace_id,
            owner_id=owner_id,
        )
        db.execute = AsyncMock(return_value=workspace_result)

        with pytest.raises(ForbiddenError):
            await list_surfaces_for_workspace(workspace_id, other_user_id, db)

        assert db.execute.await_count == 1
