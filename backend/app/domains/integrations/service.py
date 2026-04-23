"""
OAuth integration service.

Handles the full OAuth lifecycle:
  1. Initiating authorization (generate URL + CSRF state token)
  2. Handling the callback (exchange code, fetch user info, upsert account)
  3. Listing and disconnecting connected accounts
  4. Resolving / refreshing access tokens for downstream use (connectors, ingestion)

Security invariants:
  - State tokens are single-use (popped from Redis on first use).
  - State tokens carry user_id so we can tie the callback to the initiating user.
  - Tokens are never logged. Logging helpers explicitly omit token fields.
  - Refresh is attempted automatically when token_expires_at is within 60 seconds.
  - Disconnect soft-deletes (is_active=False) — tokens are zeroed so they cannot
    be decrypted even if the row is read directly from the DB.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.crypto import decrypt_token, encrypt_token
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.domains.integrations.providers import PROVIDERS, OAuthProvider
from app.models.integration import ConnectedAccount

logger = structlog.get_logger(__name__)

# State token TTL in Redis (seconds) — 5 minutes is sufficient for a human OAuth flow
_OAUTH_STATE_TTL = 300
_OAUTH_STATE_KEY_PREFIX = "oauth_state:"

# Token refresh buffer — refresh if expiry is within this many seconds
_TOKEN_REFRESH_BUFFER_SECONDS = 60


# ─── Public service functions ─────────────────────────────────────────────────


async def initiate_oauth(
    provider: str,
    user_id: str,
    db: AsyncSession,  # noqa: ARG001 — kept for interface consistency
    redis,
) -> str:
    """
    Generate an OAuth authorization URL for the given provider.

    Stores a short-lived CSRF state token in Redis keyed to the initiating
    user. Returns the full authorization URL the client should redirect to.

    Raises ValidationError for unknown providers.
    """
    provider_cfg = _get_provider(provider)
    settings = get_settings()

    # Generate a CSRF state token: "{random_hex}:{user_id}"
    random_part = secrets.token_hex(24)
    state = f"{random_part}:{user_id}"

    await redis.setex(_OAUTH_STATE_KEY_PREFIX + random_part, _OAUTH_STATE_TTL, user_id)

    redirect_uri = _redirect_uri(provider, settings)
    auth_url = _build_auth_url(provider_cfg, state, redirect_uri, settings)

    logger.info("oauth_initiated", provider=provider, user_id=user_id)
    return auth_url


async def handle_callback(
    provider: str,
    code: str,
    state: str,
    db: AsyncSession,
    redis,
) -> ConnectedAccount:
    """
    Handle the OAuth callback from a provider.

    Steps:
    1. Verify and consume the CSRF state token from Redis.
    2. Exchange the authorization code for tokens.
    3. Fetch provider user info to get account ID and username.
    4. Upsert the ConnectedAccount (create or update tokens).
    5. Return the persisted ConnectedAccount.

    Raises ValidationError if the state token is invalid or expired.
    """
    provider_cfg = _get_provider(provider)
    settings = get_settings()

    # ── 1. Validate and consume state ────────────────────────────────────────
    state_parts = state.split(":", 1)
    if len(state_parts) != 2:
        raise ValidationError("Invalid OAuth state parameter")

    random_part, user_id_str = state_parts
    stored_user_id = await redis.getdel(_OAUTH_STATE_KEY_PREFIX + random_part)
    if stored_user_id is None:
        raise ValidationError("OAuth state token expired or already used")

    if stored_user_id != user_id_str:
        logger.warning(
            "oauth_state_user_mismatch",
            provider=provider,
            expected=stored_user_id,
            received=user_id_str,
        )
        raise ValidationError("OAuth state parameter mismatch")

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise ValidationError("OAuth state contains invalid user ID")

    # ── 2. Exchange code for tokens ───────────────────────────────────────────
    redirect_uri = _redirect_uri(provider, settings)
    token_data = await _exchange_code(provider_cfg, code, redirect_uri, settings)

    access_token: str = token_data.get("access_token", "")
    refresh_token: str | None = token_data.get("refresh_token")
    expires_in: int | None = token_data.get("expires_in")
    granted_scopes: str | None = token_data.get("scope")

    if not access_token:
        raise ValidationError(f"No access_token in OAuth response from {provider}")

    token_expires_at: datetime | None = None
    if expires_in:
        token_expires_at = datetime.now(UTC) + timedelta(seconds=int(expires_in))

    # ── 3. Fetch provider user info ───────────────────────────────────────────
    provider_account_id, provider_username = await _fetch_user_info(
        provider_cfg, access_token, settings
    )

    # ── 4. Upsert ConnectedAccount ────────────────────────────────────────────
    result = await db.execute(
        select(ConnectedAccount).where(
            ConnectedAccount.user_id == user_id,
            ConnectedAccount.provider == provider,
            ConnectedAccount.provider_account_id == provider_account_id,
        )
    )
    account = result.scalar_one_or_none()

    if account is None:
        account = ConnectedAccount(
            user_id=user_id,
            provider=provider,
            provider_account_id=provider_account_id,
        )
        db.add(account)

    account.provider_username = provider_username
    account.access_token_encrypted = encrypt_token(access_token)
    account.refresh_token_encrypted = encrypt_token(refresh_token) if refresh_token else None
    account.token_expires_at = token_expires_at
    account.scopes = granted_scopes
    account.is_active = True
    account.updated_at = datetime.now(UTC)

    await db.flush()

    logger.info(
        "oauth_connected",
        provider=provider,
        user_id=str(user_id),
        provider_account_id=provider_account_id,
        provider_username=provider_username,
    )

    return account


async def get_connected_accounts(
    user_id: str,
    db: AsyncSession,
) -> list[ConnectedAccount]:
    """List all active connected accounts for a user."""
    result = await db.execute(
        select(ConnectedAccount).where(
            ConnectedAccount.user_id == uuid.UUID(user_id),
            ConnectedAccount.is_active.is_(True),
        )
    )
    return list(result.scalars().all())


async def disconnect_account(
    account_id: str,
    user_id: str,
    db: AsyncSession,
) -> None:
    """
    Disconnect a connected account.

    Verifies ownership, then soft-deletes: sets is_active=False and zeroes the
    encrypted tokens so they are unrecoverable even via direct DB access.
    """
    result = await db.execute(
        select(ConnectedAccount).where(ConnectedAccount.id == uuid.UUID(account_id))
    )
    account = result.scalar_one_or_none()

    if account is None:
        raise NotFoundError(f"Connected account {account_id} not found")

    if str(account.user_id) != user_id:
        raise ForbiddenError("You do not own this connected account")

    # Zero the tokens before marking inactive — belt-and-suspenders protection
    account.access_token_encrypted = ""
    account.refresh_token_encrypted = None
    account.is_active = False
    account.updated_at = datetime.now(UTC)

    await db.flush()
    logger.info(
        "oauth_disconnected",
        provider=account.provider,
        user_id=user_id,
        account_id=account_id,
    )


async def resolve_access_token(
    connected_account_id: str,
    db: AsyncSession,
) -> str:
    """
    Decrypt and return the access token for a connected account.

    If the token is within _TOKEN_REFRESH_BUFFER_SECONDS of expiry, attempts
    a refresh before returning. Raises NotFoundError if the account is missing
    or inactive.
    """
    result = await db.execute(
        select(ConnectedAccount).where(
            ConnectedAccount.id == uuid.UUID(connected_account_id),
            ConnectedAccount.is_active.is_(True),
        )
    )
    account = result.scalar_one_or_none()

    if account is None:
        raise NotFoundError(f"Connected account {connected_account_id} not found or inactive")

    return await refresh_token_if_needed(account, db)


async def refresh_token_if_needed(
    account: ConnectedAccount,
    db: AsyncSession,
) -> str:
    """
    Return the decrypted access token, refreshing first if near expiry.

    GitHub classic tokens do not expire — no refresh attempted.
    GitLab and Google issue expiring tokens with refresh tokens.

    Token is never returned as a log entry — callers must handle it securely.
    """
    # GitHub tokens don't expire
    if account.provider == "github":
        return decrypt_token(account.access_token_encrypted)

    # Check if we need to refresh
    needs_refresh = False
    if account.token_expires_at is not None:
        now = datetime.now(UTC)
        # Normalize: make token_expires_at tz-aware if it isn't (defensive)
        exp = account.token_expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=UTC)
        time_remaining = (exp - now).total_seconds()
        if time_remaining <= _TOKEN_REFRESH_BUFFER_SECONDS:
            needs_refresh = True

    if not needs_refresh:
        return decrypt_token(account.access_token_encrypted)

    # Attempt refresh
    if not account.refresh_token_encrypted:
        logger.warning(
            "oauth_token_expired_no_refresh",
            provider=account.provider,
            account_id=str(account.id),
        )
        # Return the expired token and let the downstream call fail with a 401
        return decrypt_token(account.access_token_encrypted)

    settings = get_settings()
    provider_cfg = _get_provider(account.provider)

    refresh_token = decrypt_token(account.refresh_token_encrypted)
    token_url = _resolve_url(provider_cfg.token_url, settings)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                token_url,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": _client_id(account.provider, settings),
                    "client_secret": _client_secret(account.provider, settings),
                },
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            token_data = resp.json()
    except httpx.HTTPError as exc:
        logger.error(
            "oauth_refresh_failed",
            provider=account.provider,
            account_id=str(account.id),
            error=str(exc),
        )
        # Return the stale token — downstream call will surface the 401
        return decrypt_token(account.access_token_encrypted)

    new_access_token = token_data.get("access_token", "")
    if not new_access_token:
        logger.error(
            "oauth_refresh_no_access_token",
            provider=account.provider,
            account_id=str(account.id),
        )
        return decrypt_token(account.access_token_encrypted)

    new_refresh_token: str | None = token_data.get("refresh_token")
    expires_in: int | None = token_data.get("expires_in")

    account.access_token_encrypted = encrypt_token(new_access_token)
    if new_refresh_token:
        account.refresh_token_encrypted = encrypt_token(new_refresh_token)
    if expires_in:
        account.token_expires_at = datetime.now(UTC) + timedelta(seconds=int(expires_in))

    account.updated_at = datetime.now(UTC)
    await db.flush()

    logger.info(
        "oauth_token_refreshed",
        provider=account.provider,
        account_id=str(account.id),
    )
    return new_access_token


# ─── Internal helpers ─────────────────────────────────────────────────────────


def _get_provider(provider: str) -> OAuthProvider:
    """Look up provider config; raise ValidationError for unknown names."""
    cfg = PROVIDERS.get(provider)
    if cfg is None:
        raise ValidationError(
            f"Unknown OAuth provider '{provider}'. "
            f"Supported: {', '.join(PROVIDERS)}"
        )
    return cfg


def _redirect_uri(provider: str, settings) -> str:
    """Build the OAuth redirect URI registered with the provider."""
    return f"{settings.oauth_redirect_base}/api/v1/integrations/{provider}/callback"


def _resolve_url(url_template: str, settings) -> str:
    """Fill GitLab URL templates; pass through concrete URLs unchanged."""
    return url_template.format(gitlab_base_url=settings.gitlab_base_url)


def _build_auth_url(
    provider: OAuthProvider,
    state: str,
    redirect_uri: str,
    settings,
) -> str:
    """Build the full provider authorization URL."""
    base_url = _resolve_url(provider.auth_url, settings)
    params: dict[str, str] = {
        "client_id": _client_id(provider.name, settings),
        "redirect_uri": redirect_uri,
        "scope": " ".join(provider.scopes),
        "state": state,
    }

    if provider.name == "google_drive":
        # Google requires response_type and access_type for offline (refresh token) access
        params["response_type"] = "code"
        params["access_type"] = "offline"
        params["prompt"] = "consent"
    elif provider.name == "github":
        params["response_type"] = "code"
    elif provider.name == "gitlab":
        params["response_type"] = "code"

    return f"{base_url}?{urlencode(params)}"


async def _exchange_code(
    provider: OAuthProvider,
    code: str,
    redirect_uri: str,
    settings,
) -> dict:
    """POST the authorization code to the provider's token endpoint."""
    token_url = _resolve_url(provider.token_url, settings)
    payload = {
        "client_id": _client_id(provider.name, settings),
        "client_secret": _client_secret(provider.name, settings),
        "code": code,
        "redirect_uri": redirect_uri,
    }
    if provider.name == "gitlab":
        payload["grant_type"] = "authorization_code"
    elif provider.name == "google_drive":
        payload["grant_type"] = "authorization_code"

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            token_url,
            data=payload,
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()

    # GitHub returns application/x-www-form-urlencoded by default; Accept: application/json
    # forces JSON. Both GitLab and Google return JSON natively.
    return resp.json()


async def _fetch_user_info(
    provider: OAuthProvider,
    access_token: str,
    settings,
) -> tuple[str, str | None]:
    """
    Fetch user info from the provider to get provider_account_id and username.

    Returns (provider_account_id, provider_username).
    provider_account_id is always the provider's canonical numeric/string user ID.
    """
    user_info_url = _resolve_url(provider.user_info_url, settings)

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            user_info_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    if provider.name == "github":
        # GitHub user API returns {"id": 12345, "login": "username"}
        account_id = str(data.get("id", ""))
        username = data.get("login")
    elif provider.name == "gitlab":
        # GitLab user API returns {"id": 12345, "username": "name"}
        account_id = str(data.get("id", ""))
        username = data.get("username")
    elif provider.name == "google_drive":
        # Google userinfo returns {"id": "12345...", "name": "Display Name"}
        account_id = str(data.get("id", ""))
        username = data.get("name")
    else:
        account_id = str(data.get("id", ""))
        username = data.get("login") or data.get("username") or data.get("name")

    if not account_id:
        raise ValidationError(
            f"Could not extract account ID from {provider.name} user info response"
        )

    return account_id, username


def _client_id(provider: str, settings) -> str:
    mapping = {
        "github": settings.github_client_id,
        "gitlab": settings.gitlab_client_id,
        "google_drive": settings.google_client_id,
    }
    return mapping.get(provider, "")


def _client_secret(provider: str, settings) -> str:
    mapping = {
        "github": settings.github_client_secret,
        "gitlab": settings.gitlab_client_secret,
        "google_drive": settings.google_client_secret,
    }
    return mapping.get(provider, "")
