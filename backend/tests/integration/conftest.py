"""
Integration test fixtures — require running Postgres (see ``make up`` / ``make test-integration``).

Uses the same ``DATABASE_URL`` as the backend container when tests run under Docker Compose.
"""

from __future__ import annotations

import pytest_asyncio

from app.core.db import engine, get_async_session


@pytest_asyncio.fixture(autouse=True)
async def _dispose_engine_after_integration_case():
    """Release asyncpg connections tied to the current asyncio loop between integration tests."""
    yield
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session():
    """Yield an async SQLAlchemy session (Postgres required — see ``make test-integration``)."""
    async with get_async_session() as session:
        yield session
