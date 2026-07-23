from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models import Invite, Role, User, UserStatus, Workspace


@pytest.mark.asyncio
async def test_user_status_has_pending():
    assert UserStatus.pending.value == "pending"


@pytest.mark.asyncio
async def test_invite_user_id_nullable_and_linkable(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    pending_user = User(workspace_id=ws.id, email="p@a.vn", password_hash="x",
                        full_name="Pending Duy", role=Role.employee,
                        status=UserStatus.pending)
    db_session.add_all([ceo, pending_user])
    await db_session.flush()

    now = datetime.now(timezone.utc)
    invite_without_user = Invite(workspace_id=ws.id, token="TOKENOLD1", role=Role.employee,
                                 created_by=ceo.id, expires_at=now)
    invite_with_user = Invite(workspace_id=ws.id, token="TOKENNEW1", role=Role.employee,
                              created_by=ceo.id, user_id=pending_user.id, expires_at=now)
    db_session.add_all([invite_without_user, invite_with_user])
    await db_session.commit()

    found = (await db_session.execute(select(Invite).where(
        Invite.token == "TOKENNEW1"))).scalar_one()
    assert found.user_id == pending_user.id

    found_old = (await db_session.execute(select(Invite).where(
        Invite.token == "TOKENOLD1"))).scalar_one()
    assert found_old.user_id is None
