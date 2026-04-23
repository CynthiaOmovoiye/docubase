"""
Fernet-based token encryption.

Used to encrypt OAuth access and refresh tokens at rest in the database.
The Fernet key is derived from settings.app_secret_key using SHA-256 so the
encryption key never appears in configuration directly.

Why Fernet:
- Authenticated encryption (AES-128-CBC + HMAC-SHA256) — tampering detected.
- Symmetric — we need to decrypt tokens to pass them to provider APIs.
- Key derivation via SHA-256 produces exactly 32 bytes → base64url-encode → valid Fernet key.
"""

import base64
import hashlib

from cryptography.fernet import Fernet

from app.core.config import get_settings


def _make_fernet() -> Fernet:
    """Derive a Fernet instance from the application secret key."""
    key_bytes = hashlib.sha256(get_settings().app_secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key_bytes))


def encrypt_token(plain: str) -> str:
    """Encrypt a plaintext token string. Returns a URL-safe base64-encoded ciphertext."""
    return _make_fernet().encrypt(plain.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    """Decrypt a Fernet-encrypted token string. Raises InvalidToken if tampered."""
    return _make_fernet().decrypt(encrypted.encode()).decode()
