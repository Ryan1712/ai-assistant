import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import Notification, Project, Report, Role, User, Workspace, WorkspacePlan
from app.services import report_schedule_service as svc

NOW = datetime(2026, 7, 13, 8, 0, tzinfo=timezone.utc)

_seq = iter(range(2000))


async def _setup(db):
    n = next(_seq)
    ws = Workspace(name=f"W{n}", plan=WorkspacePlan.advanced)
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email=f"c{n}@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    await db.commit()
    return ws, ceo


@pytest.mark.asyncio
async def test_due_schedule_generates_report_and_notifies(db_session, storage_dir):
    ws, ceo = await _setup(db_session)
    sched = await svc.create_schedule(db_session, ceo, weekday=None, hour=8, minute=0)
    sched.next_run_at = NOW - timedelta(minutes=1)  # ép tới hạn
    await db_session.commit()

    results = await svc.run_due_schedules(db_session, now=NOW)

    assert len(results) == 1
    assert results[0]["schedule_id"] == str(sched.id)
    report = await db_session.get(Report, uuid.UUID(results[0]["report_id"]))
    assert report is not None and report.workspace_id == ws.id

    notifs = (await db_session.execute(select(Notification).where(
        Notification.recipient_id == ceo.id))).scalars().all()
    assert len(notifs) == 1
    assert notifs[0].type == "scheduled_report"
    assert notifs[0].payload["report_id"] == results[0]["report_id"]

    await db_session.refresh(sched)
    # SQLite không giữ tzinfo khi đọc lại — so sánh naive.
    assert sched.last_run_at == NOW.replace(tzinfo=None)
    assert sched.next_run_at == (NOW + timedelta(days=1)).replace(tzinfo=None)


@pytest.mark.asyncio
async def test_future_schedule_does_not_run(db_session, storage_dir):
    ws, ceo = await _setup(db_session)
    sched = await svc.create_schedule(db_session, ceo, weekday=None, hour=8, minute=0)
    sched.next_run_at = NOW + timedelta(hours=1)
    await db_session.commit()

    results = await svc.run_due_schedules(db_session, now=NOW)

    assert results == []
    count = (await db_session.execute(select(Report))).scalars().all()
    assert count == []


@pytest.mark.asyncio
async def test_inactive_schedule_does_not_run_even_if_due(db_session, storage_dir):
    ws, ceo = await _setup(db_session)
    sched = await svc.create_schedule(db_session, ceo, weekday=None, hour=8, minute=0)
    sched.next_run_at = NOW - timedelta(minutes=1)
    sched.active = False
    await db_session.commit()

    results = await svc.run_due_schedules(db_session, now=NOW)

    assert results == []


@pytest.mark.asyncio
async def test_two_due_schedules_in_different_workspaces_both_run(db_session, storage_dir):
    ws1, ceo1 = await _setup(db_session)
    ws2, ceo2 = await _setup(db_session)
    s1 = await svc.create_schedule(db_session, ceo1, weekday=None, hour=8)
    s2 = await svc.create_schedule(db_session, ceo2, weekday=None, hour=8)
    s1.next_run_at = NOW - timedelta(minutes=1)
    s2.next_run_at = NOW - timedelta(minutes=1)
    await db_session.commit()

    results = await svc.run_due_schedules(db_session, now=NOW)

    assert {r["schedule_id"] for r in results} == {str(s1.id), str(s2.id)}
    reports = {r.workspace_id for r in
              (await db_session.execute(select(Report))).scalars().all()}
    assert reports == {ws1.id, ws2.id}
