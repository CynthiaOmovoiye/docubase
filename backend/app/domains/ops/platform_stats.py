"""Read-only platform counters for superuser dashboards (Phase 7)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.source import Source
from app.models.twin import Twin
from app.models.user import User
from app.models.workspace import Workspace


async def fetch_platform_stats(db: AsyncSession) -> dict[str, Any]:
    users = int((await db.execute(select(func.count()).select_from(User))).scalar_one())
    workspaces = int((await db.execute(select(func.count()).select_from(Workspace))).scalar_one())
    twins = int((await db.execute(select(func.count()).select_from(Twin))).scalar_one())
    sources_total = int((await db.execute(select(func.count()).select_from(Source))).scalar_one())

    rows = (await db.execute(select(Source.status, func.count()).group_by(Source.status))).all()
    sources_by_status: dict[str, int] = {}
    for status, count in rows:
        key = status.value if hasattr(status, "value") else str(status)
        sources_by_status[key] = int(count)

    return {
        "users": users,
        "workspaces": workspaces,
        "twins": twins,
        "sources_total": sources_total,
        "sources_by_status": sources_by_status,
    }
