#!/usr/bin/env python3
"""
Seed dev data — optional superuser for the owner console /admin API.

Set in `.env` (root of repo):

  SEED_ADMIN_EMAIL=admin@example.com
  SEED_ADMIN_PASSWORD=your-secure-password   # min 8 chars, not all digits

If the user already exists, they are promoted to superuser (password is not changed).
If the user is new, they are created with the given password and a default workspace.

Run: `make seed` — sets `PYTHONPATH=/app` so `app` resolves inside Docker.

Locally from `backend/`: `PYTHONPATH=. python scripts/seed.py`
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from sqlalchemy import select

from app.core.db import AsyncSessionLocal
from app.core.security import hash_password
from app.domains.users.service import _default_slug, _unique_workspace_slug
from app.models.user import User
from app.models.workspace import Workspace

# backend root = …/backend (in Docker: /app). Repo root = backend.parent when using a full checkout.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv_best_effort() -> None:
    """Load `.env` from disk when vars are not only in the process environment."""
    try:
        from dotenv import load_dotenv  # type: ignore[import]
    except ImportError:
        return
    candidates = (
        _BACKEND_ROOT / "project.env",  # docker-compose bind-mount of repo `.env` → `/app/project.env`
        _BACKEND_ROOT.parent / ".env",  # project root (host checkout next to backend/)
        _BACKEND_ROOT / ".env",  # backend/.env
    )
    for path in candidates:
        if path.is_file():
            load_dotenv(path, override=False)
            return


def _password_ok(pw: str) -> bool:
    return 8 <= len(pw) <= 128 and not pw.isdigit()


async def _run() -> None:
    _load_dotenv_best_effort()

    email = (os.environ.get("SEED_ADMIN_EMAIL") or "").strip().lower()
    password = os.environ.get("SEED_ADMIN_PASSWORD") or ""

    if not email or not password:
        print(
            "Skipping admin seed: set SEED_ADMIN_EMAIL and SEED_ADMIN_PASSWORD in your "
            "project `.env` (repo root; see .env.example), then run `make seed` again.\n"
            "Under Docker the same file is mounted at `/app/project.env`; restart the backend "
            "if variables were only added to the process environment list."
        )
        return

    if not _password_ok(password):
        print("SEED_ADMIN_PASSWORD must be 8–128 characters and not all digits.", file=sys.stderr)
        sys.exit(1)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user:
            if not user.is_superuser:
                user.is_superuser = True
                db.add(user)
                await db.commit()
                print(f"Promoted existing user to superuser: {email}")
            else:
                print(f"User already superuser: {email}")
            return

        user = User(
            email=email,
            hashed_password=hash_password(password),
            display_name="Platform admin",
            is_verified=True,
            is_superuser=True,
        )
        db.add(user)
        await db.flush()

        base = _default_slug(user.display_name, email)
        workspace = Workspace(
            name="Admin workspace",
            slug=await _unique_workspace_slug(base, db),
            owner_id=user.id,
        )
        db.add(workspace)
        await db.commit()
        print(f"Created superuser and default workspace: {email}")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
