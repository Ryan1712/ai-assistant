import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import Notification, Project, Role, Task, TaskAssignee, TaskStatus, User, Workspace
from app.services import work_service as svc

NOW = datetime(2026, 7, 18, 8, 0, tzinfo=timezone.utc)

_seq = iter(range(3000))


async def _setup(db):
    n = next(_seq)
    ws = Workspace(name=f"W{n}")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email=f"c{n}@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    emp = User(workspace_id=ws.id, email=f"e{n}@a.vn", password_hash="x", full_name="E",
              role=Role.employee)
    db.add_all([ceo, emp])
    await db.flush()
    project = Project(workspace_id=ws.id, name="P", created_by=ceo.id)
    db.add(project)
    await db.flush()
    await db.commit()
    return ws, ceo, emp, project


@pytest.mark.asyncio
async def test_task_due_within_24h_notifies_assignees(db_session):
    ws, ceo, emp, project = await _setup(db_session)
    task = Task(workspace_id=ws.id, project_id=project.id, title="T",
               deadline=NOW + timedelta(hours=5), created_by=ceo.id)
    db_session.add(task)
    await db_session.flush()
    db_session.add(TaskAssignee(workspace_id=ws.id, task_id=task.id, user_id=emp.id))
    await db_session.commit()

    count = await svc.notify_upcoming_deadlines(db_session, now=NOW)
    assert count == 1

    notifs = (await db_session.execute(select(Notification).where(
        Notification.recipient_id == emp.id))).scalars().all()
    assert len(notifs) == 1
    assert notifs[0].type == "task_due_soon"
    assert notifs[0].payload["task_id"] == str(task.id)

    await db_session.refresh(task)
    assert task.deadline_reminder_sent_at is not None


@pytest.mark.asyncio
async def test_task_due_far_away_not_notified(db_session):
    ws, ceo, emp, project = await _setup(db_session)
    task = Task(workspace_id=ws.id, project_id=project.id, title="T",
               deadline=NOW + timedelta(days=5), created_by=ceo.id)
    db_session.add(task)
    await db_session.flush()
    db_session.add(TaskAssignee(workspace_id=ws.id, task_id=task.id, user_id=emp.id))
    await db_session.commit()

    count = await svc.notify_upcoming_deadlines(db_session, now=NOW)
    assert count == 0


@pytest.mark.asyncio
async def test_done_task_not_notified(db_session):
    ws, ceo, emp, project = await _setup(db_session)
    task = Task(workspace_id=ws.id, project_id=project.id, title="T", status=TaskStatus.done,
               deadline=NOW + timedelta(hours=5), created_by=ceo.id)
    db_session.add(task)
    await db_session.commit()

    count = await svc.notify_upcoming_deadlines(db_session, now=NOW)
    assert count == 0


@pytest.mark.asyncio
async def test_already_reminded_task_not_notified_again(db_session):
    ws, ceo, emp, project = await _setup(db_session)
    task = Task(workspace_id=ws.id, project_id=project.id, title="T",
               deadline=NOW + timedelta(hours=5), created_by=ceo.id,
               deadline_reminder_sent_at=NOW - timedelta(hours=1))
    db_session.add(task)
    await db_session.commit()

    count = await svc.notify_upcoming_deadlines(db_session, now=NOW)
    assert count == 0


@pytest.mark.asyncio
async def test_worker_cron_registered():
    from app.agent.worker import WorkerSettings, check_task_deadlines

    names = [j.name for j in WorkerSettings.cron_jobs]
    assert "cron:check_task_deadlines" in names
    job = next(j for j in WorkerSettings.cron_jobs if j.name == "cron:check_task_deadlines")
    assert job.coroutine is check_task_deadlines


@pytest.mark.asyncio
async def test_check_task_deadlines_calls_notify_upcoming_deadlines(engine, monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.agent import worker as worker_module

    called = {}

    async def fake_notify(db, **kwargs):
        called["db"] = db
        return 0

    monkeypatch.setattr(worker_module.work_service, "notify_upcoming_deadlines", fake_notify)
    ctx = {"session_factory": async_sessionmaker(engine, expire_on_commit=False)}

    await worker_module.check_task_deadlines(ctx)

    assert "db" in called
