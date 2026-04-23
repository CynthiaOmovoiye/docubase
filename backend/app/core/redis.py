"""
Redis client and token revocation helpers.

Uses a module-level connection pool so the same client is reused across
requests. Call close_redis() on app shutdown if needed.

Token revocation:
  - Each refresh token carries a `jti` (JWT ID) claim — a random UUID.
  - On issue, the jti is NOT stored (stateless by default).
  - On logout OR token rotation, the jti is written to Redis with a TTL
    equal to the token's remaining lifetime.
  - On refresh, the jti is checked against the revocation set before
    issuing a new token pair.  A revoked jti is rejected with 401.

Key format: "revoked_jti:{jti}"  — value is "1", TTL = remaining seconds.
"""

from __future__ import annotations

import redis.asyncio as aioredis

from app.core.config import get_settings

settings = get_settings()

_redis_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    """Return (and lazily create) the module-level Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    return _redis_client


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


# ─── Token revocation ─────────────────────────────────────────────────────────

_REVOKED_KEY_PREFIX = "revoked_jti:"


async def revoke_refresh_token(jti: str, ttl_seconds: int) -> None:
    """
    Mark a refresh token's jti as revoked.

    ttl_seconds should equal the remaining lifetime of the token so Redis
    automatically purges the key after expiry (no unbounded growth).
    """
    if ttl_seconds <= 0:
        # Token is already expired — nothing to revoke.
        return
    client = get_redis()
    await client.setex(_REVOKED_KEY_PREFIX + jti, ttl_seconds, "1")


async def is_refresh_token_revoked(jti: str) -> bool:
    """Return True if the jti has been revoked."""
    client = get_redis()
    return await client.exists(_REVOKED_KEY_PREFIX + jti) == 1
