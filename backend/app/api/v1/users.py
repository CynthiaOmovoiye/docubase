"""
User and auth endpoints.

POST /users/register   — create account
POST /users/login      — get token pair
POST /users/refresh    — rotate tokens
POST /users/logout     — revoke refresh token
GET  /users/me         — current user profile
PATCH /users/me        — update profile
"""

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.limiter import limiter
from app.domains.users.service import (
    login_user,
    logout_user,
    refresh_tokens,
    register_user,
    update_user,
)
from app.models.user import User
from app.schemas.users import (
    RefreshTokenRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
    UserUpdateRequest,
)

router = APIRouter()


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(
    request: Request,  # required by slowapi
    payload: UserRegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Register a new account. Auto-creates a default workspace."""
    _user, tokens = await register_user(payload, db)
    return tokens


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,  # required by slowapi
    payload: UserLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate with email + password. Returns access + refresh tokens."""
    _user, tokens = await login_user(payload, db)
    return tokens


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("20/minute")
async def refresh(
    request: Request,  # required by slowapi
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Exchange a valid refresh token for a new token pair. The submitted token is rotated (revoked)."""
    return await refresh_tokens(payload.refresh_token, db)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: RefreshTokenRequest,
) -> None:
    """
    Revoke the supplied refresh token server-side.

    The client should also clear its local access token after calling this.
    Silently succeeds even if the token is already expired.
    """
    await logout_user(payload.refresh_token)


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> User:
    """Return the authenticated user's profile."""
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_me(
    payload: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Update the authenticated user's profile."""
    return await update_user(current_user, payload, db)
