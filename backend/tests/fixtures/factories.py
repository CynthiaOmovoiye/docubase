"""
Test data factories.

Use these in tests instead of constructing model instances manually.
Keeps test setup clean and consistent.
"""

import uuid
from datetime import UTC, datetime


def make_user(**overrides) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "email": "test@example.com",
        "display_name": "Test User",
        "is_active": True,
        "is_verified": True,
        "created_at": datetime.now(UTC).isoformat(),
        **overrides,
    }


def make_workspace(**overrides) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "name": "Test Workspace",
        "slug": "test-workspace",
        "description": None,
        "owner_id": str(uuid.uuid4()),
        "created_at": datetime.now(UTC).isoformat(),
        **overrides,
    }


def make_twin(**overrides) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "name": "Test Twin",
        "slug": "test-twin",
        "description": "A test twin",
        "is_active": True,
        "workspace_id": str(uuid.uuid4()),
        "created_at": datetime.now(UTC).isoformat(),
        **overrides,
    }


def make_source(**overrides) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "name": "Test Source",
        "source_type": "markdown",
        "status": "pending",
        "twin_id": str(uuid.uuid4()),
        "connection_config": {},
        "created_at": datetime.now(UTC).isoformat(),
        **overrides,
    }


def make_raw_file(**overrides) -> dict:
    return {
        "path": "README.md",
        "content": "# Test Project\nThis is a test.",
        "size_bytes": 30,
        "metadata": {},
        **overrides,
    }
