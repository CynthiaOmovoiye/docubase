"""
FastAPI dependencies.

get_current_user  — validates JWT and returns the authenticated User.
get_current_workspace — resolves a workspace and checks ownership.
"""

import uuid

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from app.core.security import decode_token
from app.models.user import User
from app.models.workspace import Workspace


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Extract and validate Bearer token from Authorization header.
    Returns the authenticated User or raises UnauthorizedError.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError("Missing or malformed Authorization header")

    token = authorization.removeprefix("Bearer ").strip()
    payload = decode_token(token, expected_type="access")  # raises UnauthorizedError on failure

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise UnauthorizedError("Token has no subject")

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise UnauthorizedError("Invalid token subject")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise UnauthorizedError("User not found")
    if not user.is_active:
        raise UnauthorizedError("Account is inactive")

    return user


async def get_superuser(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Require the authenticated user to be a superuser.
    Raises ForbiddenError for any non-superuser (including authenticated regular users).
    """
    if not current_user.is_superuser:
        raise ForbiddenError("Superuser access required")
    return current_user


async def get_workspace_for_user(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Workspace:
    """
    Resolve a workspace by ID and assert the current user owns it.
    Raises NotFoundError or ForbiddenError as appropriate.

    Important: we always raise NotFoundError for non-existent workspaces
    rather than ForbiddenError — don't leak whether a workspace exists
    to someone who doesn't own it.
    """
    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id)
    )
    workspace = result.scalar_one_or_none()

    if workspace is None or workspace.owner_id != current_user.id:
        raise NotFoundError(f"Workspace {workspace_id} not found")

    return workspace
