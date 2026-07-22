from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import Directive, DirectiveStatus, Notification, Role, User, Workspace
from app.services import directive_service


async def _world(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    duy = User(workspace_id=ws.id, email="d@a.vn", password_hash="x", full_name="Duy",
              role=Role.employee)
    db.add_all([ceo, duy])
    await db.flush()
    await db.commit()
    return ws, ceo, duy


def _make_directive(ws, ceo, duy, created_at, remind_count=0, escalated_at=None):
    return Directive(workspace_id=ws.id, created_by=ceo.id, recipient_id=duy.id,
                     verbatim_text="x", created_at=created_at, remind_count=remind_count,
                     escalated_at=escalated_at)


@pytest.mark.asyncio
async def test_reminds_recipient_after_24h_unacked(db_session):
    ws, ceo, duy = await _world(db_session)
    now = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
    d = _make_directive(ws, ceo, duy, now - timedelta(hours=25))
    db_session.add(d)
    await db_session.commit()

    count = await directive_service.escalate_overdue(db_session, now=now)

    assert count == 1
    await db_session.refresh(d)
    assert d.remind_count == 1
    notif = (await db_session.execute(
        select(Notification).where(Notification.type == "directive_reminder"))).scalar_one()
    assert notif.recipient_id == duy.id


@pytest.mark.asyncio
async def test_does_not_remind_twice(db_session):
    ws, ceo, duy = await _world(db_session)
    now = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
    d = _make_directive(ws, ceo, duy, now - timedelta(hours=25), remind_count=1)
    db_session.add(d)
    await db_session.commit()

    count = await directive_service.escalate_overdue(db_session, now=now)

    assert count == 0
    rows = (await db_session.execute(
        select(Notification).where(Notification.type == "directive_reminder"))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_escalates_to_creator_after_48h_if_already_reminded(db_session):
    ws, ceo, duy = await _world(db_session)
    now = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
    d = _make_directive(ws, ceo, duy, now - timedelta(hours=49), remind_count=1)
    db_session.add(d)
    await db_session.commit()

    count = await directive_service.escalate_overdue(db_session, now=now)

    assert count == 1
    await db_session.refresh(d)
    assert d.escalated_at is not None
    notif = (await db_session.execute(
        select(Notification).where(Notification.type == "directive_escalation"))).scalar_one()
    assert notif.recipient_id == ceo.id


@pytest.mark.asyncio
async def test_does_not_escalate_twice(db_session):
    ws, ceo, duy = await _world(db_session)
    now = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
    d = _make_directive(ws, ceo, duy, now - timedelta(hours=49), remind_count=1,
                        escalated_at=now - timedelta(hours=1))
    db_session.add(d)
    await db_session.commit()

    count = await directive_service.escalate_overdue(db_session, now=now)

    assert count == 0


@pytest.mark.asyncio
async def test_acked_directive_never_escalated(db_session):
    ws, ceo, duy = await _world(db_session)
    now = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
    d = _make_directive(ws, ceo, duy, now - timedelta(hours=100))
    d.status = DirectiveStatus.acked
    db_session.add(d)
    await db_session.commit()

    count = await directive_service.escalate_overdue(db_session, now=now)

    assert count == 0
