"""
Security utilities: JWT issuance/verification, password hashing.

JWT library: PyJWT >= 2.8.0
  - Enforces algorithm list on decode (no algorithm confusion)
  - Raises jwt.exceptions.InvalidTokenError (and subclasses) on failure
  - jwt.encode() returns str in v2+
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt
from jwt.exceptions import InvalidTokenError

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError

settings = get_settings()


# ─── Password ─────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ─── JWT ──────────────────────────────────────────────────────────────────────

def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    expire = datetime.now(UTC) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    payload: dict[str, Any] = {"sub": subject, "exp": expire, "type": "access"}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str) -> tuple[str, str]:
    """
    Create a refresh token with an embedded jti (JWT ID) for revocation support.

    Returns (token_string, jti).
    """
    jti = str(uuid.uuid4())
    expire = datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days)
    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expire,
        "type": "refresh",
        "jti": jti,
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, jti


def decode_token(token: str, expected_type: str = "access") -> dict[str, Any]:
    """
    Decode and validate a JWT.  Raises UnauthorizedError on any failure.

    PyJWT enforces the algorithm list strictly — no algorithm confusion attacks.
    """
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except InvalidTokenError as e:
        raise UnauthorizedError("Invalid or expired token") from e

    if payload.get("type") != expected_type:
        raise UnauthorizedError("Invalid token type")

    return payload


def refresh_token_ttl_seconds(payload: dict[str, Any]) -> int:
    """Return the remaining lifetime of a decoded token in whole seconds (≥ 0)."""
    exp = payload.get("exp")
    if exp is None:
        return 0
    remaining = int(exp) - int(datetime.now(UTC).timestamp())
    return max(0, remaining)
