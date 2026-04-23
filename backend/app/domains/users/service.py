"""
User domain service.

Registration, login, token refresh, logout, profile updates.
All business logic lives here — the API layer just calls these.
"""

import re
import uuid

# Pre-computed constant-time dummy hash used in login to prevent user-enumeration
# via timing. Must be a *real* bcrypt hash so checkpw takes the same time as
# verifying an existing user's hash.
import bcrypt as _bcrypt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.redis import is_refresh_token_revoked, revoke_refresh_token
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    refresh_token_ttl_seconds,
    verify_password,
)
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.users import (
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserUpdateRequest,
)

_DUMMY_HASH: str = _bcrypt.hashpw(b"dummy-timing-sentinel", _bcrypt.gensalt()).decode()


def _default_slug(display_name: str | None, email: str) -> str:
    """Generate a workspace slug from display name or email prefix."""
    base = display_name or email.split("@")[0]
    slug = re.sub(r"[^\w]", "-", base.lower()).strip("-")
    slug = re.sub(r"-+", "-", slug)
    return slug[:60] or "workspace"


async def register_user(
    payload: UserRegisterRequest,
    db: AsyncSession,
) -> tuple[User, TokenResponse]:
    """
    Create a new user and their default workspace.
    Returns the created user and initial token pair.
    Raises ConflictError if email is already registered.
    """
    # Check uniqueness
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise ConflictError("An account with this email already exists")

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        display_name=payload.display_name,
    )
    db.add(user)
    await db.flush()  # get user.id before creating workspace

    # Auto-create a default workspace for every new user
    base_slug = _default_slug(payload.display_name, payload.email)
    workspace = Workspace(
        name=payload.display_name or payload.email.split("@")[0],
        slug=await _unique_workspace_slug(base_slug, db),
        owner_id=user.id,
    )
    db.add(workspace)
    await db.flush()

    tokens = await _issue_tokens(user)
    return user, tokens


async def login_user(
    payload: UserLoginRequest,
    db: AsyncSession,
) -> tuple[User, TokenResponse]:
    """
    Authenticate a user with email/password.
    Returns the user and a fresh token pair.
    Raises UnauthorizedError on bad credentials — never reveals which field is wrong.
    """
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    # Constant-time path: always call verify_password even on a miss to prevent
    # user-enumeration via response timing.  _DUMMY_HASH is a valid bcrypt hash
    # so checkpw takes the same CPU time as a real comparison.
    candidate_hash = user.hashed_password if user else _DUMMY_HASH

    if not verify_password(payload.password, candidate_hash) or user is None:
        raise UnauthorizedError("Invalid email or password")

    if not user.is_active:
        raise UnauthorizedError("Account is inactive")

    return user, await _issue_tokens(user)


async def refresh_tokens(
    refresh_token: str,
    db: AsyncSession,
) -> TokenResponse:
    """
    Validate a refresh token and issue a new token pair.

    The incoming refresh token's jti is revoked immediately after decoding
    (token rotation) so each refresh token can only be used once.
    """
    payload = decode_token(refresh_token, expected_type="refresh")
    user_id = uuid.UUID(payload["sub"])
    jti = payload.get("jti")

    # Reject tokens that pre-date jti support (no jti claim)
    if not jti:
        raise UnauthorizedError("Invalid refresh token")

    # Check revocation store
    if await is_refresh_token_revoked(jti):
        raise UnauthorizedError("Refresh token has been revoked")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise UnauthorizedError("Invalid refresh token")

    # Rotate: revoke the used jti before issuing new tokens
    ttl = refresh_token_ttl_seconds(payload)
    await revoke_refresh_token(jti, ttl)

    return await _issue_tokens(user)


async def logout_user(refresh_token: str) -> None:
    """
    Revoke the submitted refresh token.

    Silently succeeds even if the token is already expired or invalid —
    the important thing is that a valid token cannot be replayed.
    """
    try:
        payload = decode_token(refresh_token, expected_type="refresh")
        jti = payload.get("jti")
        if jti:
            ttl = refresh_token_ttl_seconds(payload)
            await revoke_refresh_token(jti, ttl)
    except UnauthorizedError:
        # Expired or malformed — nothing to revoke
        pass


async def update_user(
    user: User,
    payload: UserUpdateRequest,
    db: AsyncSession,
) -> User:
    """Update mutable profile fields."""
    if payload.display_name is not None:
        user.display_name = payload.display_name
    db.add(user)
    await db.flush()
    return user


# ─── Internal helpers ─────────────────────────────────────────────────────────

async def _issue_tokens(user: User) -> TokenResponse:
    refresh_token, _jti = create_refresh_token(subject=str(user.id))
    return TokenResponse(
        access_token=create_access_token(subject=str(user.id)),
        refresh_token=refresh_token,
    )


async def _unique_workspace_slug(base: str, db: AsyncSession, max_attempts: int = 10) -> str:
    """Append a short suffix until we find an unused workspace slug."""
    import random
    import string

    slug = base
    for _ in range(max_attempts):
        try:
            result = await db.execute(select(Workspace).where(Workspace.slug == slug))
            if result.scalar_one_or_none() is None:
                return slug
        except IntegrityError:
            # Concurrent insert raced us — treat as taken and try next suffix
            pass
        suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
        slug = f"{base}-{suffix}"

    raise ConflictError("Could not generate a unique workspace slug")
