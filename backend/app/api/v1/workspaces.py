"""
Workspace endpoints.

GET    /workspaces/          — list current user's workspaces
POST   /workspaces/          — create a workspace
GET    /workspaces/{id}      — get a workspace
PATCH  /workspaces/{id}      — update name/description
DELETE /workspaces/{id}      — delete workspace (and all twins within)
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.domains.workspaces.service import (
    create_workspace,
    delete_workspace,
    get_workspace,
    list_workspaces,
    update_workspace,
)
from app.models.user import User
from app.schemas.workspaces import (
    WorkspaceCreateRequest,
    WorkspaceResponse,
    WorkspaceUpdateRequest,
)

router = APIRouter()


@router.get("/", response_model=list[WorkspaceResponse])
async def list_my_workspaces(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list:
    return await list_workspaces(current_user, db)


@router.post("/", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_new_workspace(
    payload: WorkspaceCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await create_workspace(payload, current_user, db)


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_one_workspace(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_workspace(workspace_id, current_user, db)


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
async def update_one_workspace(
    workspace_id: uuid.UUID,
    payload: WorkspaceUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await update_workspace(workspace_id, payload, current_user, db)


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_one_workspace(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await delete_workspace(workspace_id, current_user, db)
