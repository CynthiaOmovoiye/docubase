"""Operator provisioning (superuser accounts without consumer workspace)."""

import uuid

import pytest
from sqlalchemy import func, select

from app.core.exceptions import ConflictError
from app.core.security import hash_password
from app.domains.users.service import create_operator_user
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.users import UserRegisterRequest


async def test_create_operator_user_is_superuser_verified_no_workspace(db_session):
    suf = uuid.uuid4().hex[:12]
    email = f"operator-{suf}@example.com"
    payload = UserRegisterRequest(
        email=email,
        password="not-all-digits-x",
        display_name="Ops Bot",
    )

    user = await create_operator_user(payload, db_session)
    await db_session.commit()

    assert user.is_superuser is True
    assert user.is_verified is True
    assert user.is_active is True
    assert user.email == email.lower()

    ws_count = (
        await db_session.execute(select(func.count()).select_from(Workspace).where(Workspace.owner_id == user.id))
    ).scalar_one()
    assert ws_count == 0


async def test_create_operator_user_conflict_when_email_exists(db_session):
    suf = uuid.uuid4().hex[:12]
    email = f"dup-{suf}@example.com"

    await create_operator_user(
        UserRegisterRequest(email=email, password="first-pass-ok"),
        db_session,
    )
    await db_session.commit()

    with pytest.raises(ConflictError):
        await create_operator_user(
            UserRegisterRequest(email=email.upper(), password="second-pass-ok"),
            db_session,
        )


async def test_consumers_only_list_excludes_superusers(db_session):
    """Mirrors GET /admin/users?consumers_only=true — signups view must omit operators."""
    suf = uuid.uuid4().hex[:8]
    op = User(
        email=f"op-{suf}@example.com",
        hashed_password=hash_password("pw-test-one"),
        is_superuser=True,
        is_verified=True,
        is_active=True,
    )
    consumer = User(
        email=f"buyer-{suf}@example.com",
        hashed_password=hash_password("pw-test-two"),
        is_superuser=False,
        is_verified=True,
        is_active=True,
    )
    db_session.add_all([op, consumer])
    await db_session.commit()

    rows = (
        await db_session.execute(
            select(User).where(User.is_superuser.is_(False)).order_by(User.created_at.desc()).limit(500)
        )
    ).scalars().all()
    emails = {u.email for u in rows}
    assert consumer.email in emails
    assert op.email not in emails
