"""
Database session management.

Async SQLAlchemy engine and session factory.
Use get_db() as a FastAPI dependency for request-scoped sessions.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    # echo=False always — SQLAlchemy echo logs bound parameter values (including
    # hashed passwords and PII).  Use SQL_DEBUG=1 in a local-only dev shell if
    # you genuinely need query tracing; never leave it on by default.
    echo=False,
    pool_pre_ping=True,  # recycle stale connections silently
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields a request-scoped async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_async_session():
    """
    Context manager for non-request-scoped sessions.

    Used by background jobs (ARQ workers) that run outside the FastAPI
    request lifecycle. Each call returns a new async context manager.

    Usage:
        async with get_async_session() as db:
            ...
    """
    return AsyncSessionLocal()
