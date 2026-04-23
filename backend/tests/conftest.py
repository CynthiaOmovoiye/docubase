"""
Shared pytest configuration.

Ensures required Settings env vars exist when tests import ``app`` modules
that load ``app.core.db`` at import time (engine creation does not connect
until first query).
"""

from __future__ import annotations

import os

os.environ.setdefault("APP_SECRET_KEY", "pytest-app-secret-key-minimum-32-chars")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://twin_user:twin_pass@localhost:5433/twin_db",
)
os.environ.setdefault("JWT_SECRET_KEY", "pytest-jwt-secret-key-minimum-32-chars")
