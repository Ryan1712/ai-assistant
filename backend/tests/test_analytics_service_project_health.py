from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.models import Project, Role, Task, TaskAssignee, TaskPriority, TaskStatus, TaskUpdate, User, Workspace
from app.services import analytics_service


async def _world(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    mgr = User(workspace_id=ws.id, email="m@a.vn", password_hash="x", full_name="M",
              role=Role.manager)
    db.add_all([ceo, mgr])
    await db.flush()
    emp = User(workspace_id=ws.id, email="e@a.vn", password_hash="x", full_name="E",
              role=Role.employee, manager_id=mgr.id)
    db.add(emp)
    await db.flush()
    project = Project(workspace_id=ws.id, name="Du an X", created_by=ceo.id, owner_id=mgr.id)
    db.add(project)
    await db.flush()
    return ws, ceo, mgr, emp, project


@pytest.mark.asyncio
async def test_project_not_visible_404(db_session):
    ws, ceo, mgr, emp, project = await _world(db_session)
    ws2 = Workspace(name="B")
    db_session.add(ws2)
    await db_session.flush()
    outsider = User(workspace_id=ws2.id, email="x@b.vn", password_hash="x", full_name="X",
                    role=Role.ceo, is_root=True)
    db_session.add(outsider)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await analytics_service.get_project_health(db_session, outsider, project.id)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_empty_project_has_note_and_low_risk(db_session):
    ws, ceo, mgr, emp, project = await _world(db_session)
    await db_session.commit()

    result = await analytics_service.get_project_health(db_session, ceo, project.id)
    assert result["task_total"] == 0
    assert result["risk"] == "low"
    assert result.get("note")


@pytest.mark.asyncio
async def test_overdue_task_makes_risk_high(db_session):
    ws, ceo, mgr, emp, project = await _world(db_session)
    now = datetime.now(timezone.utc)
    task = Task(workspace_id=ws.id, project_id=project.id, title="Trễ hạn",
               status=TaskStatus.in_progress, percent=40, priority=TaskPriority.medium,
               created_by=ceo.id, deadline=now - timedelta(days=3))
    db_session.add(task)
    await db_session.commit()

    result = await analytics_service.get_project_health(db_session, ceo, project.id, now=now)
    assert result["risk"] == "high"
    assert len(result["overdue"]) == 1
    assert result["overdue"][0]["task_id"] == str(task.id)
    assert result["overdue"][0]["days_overdue"] >= 3


@pytest.mark.asyncio
async def test_over_30_percent_blocked_makes_risk_high(db_session):
    ws, ceo, mgr, emp, project = await _world(db_session)
    now = datetime.now(timezone.utc)
    blocked = Task(workspace_id=ws.id, project_id=project.id, title="Bi chan",
                  status=TaskStatus.blocked, percent=10, priority=TaskPriority.medium,
                  created_by=ceo.id, created_at=now - timedelta(days=2))
    ok1 = Task(workspace_id=ws.id, project_id=project.id, title="OK1",
              status=TaskStatus.done, percent=100, priority=TaskPriority.medium,
              created_by=ceo.id)
    ok2 = Task(workspace_id=ws.id, project_id=project.id, title="OK2",
              status=TaskStatus.done, percent=100, priority=TaskPriority.medium,
              created_by=ceo.id)
    db_session.add_all([blocked, ok1, ok2])
    await db_session.commit()

    result = await analytics_service.get_project_health(db_session, ceo, project.id, now=now)
    assert result["risk"] == "high"
    assert len(result["blocked"]) == 1
    assert result["blocked"][0]["days_since_created"] >= 2


@pytest.mark.asyncio
async def test_stale_task_without_recent_update_makes_risk_medium(db_session):
    ws, ceo, mgr, emp, project = await _world(db_session)
    now = datetime.now(timezone.utc)
    task = Task(workspace_id=ws.id, project_id=project.id, title="Im lang lau",
               status=TaskStatus.in_progress, percent=20, priority=TaskPriority.medium,
               created_by=ceo.id, created_at=now - timedelta(days=10))
    db_session.add(task)
    await db_session.commit()

    result = await analytics_service.get_project_health(db_session, ceo, project.id, now=now)
    assert result["risk"] == "medium"
    assert len(result["stale"]) == 1
    assert result["stale"][0]["days_since_update"] >= 7


@pytest.mark.asyncio
async def test_recent_update_keeps_task_out_of_stale(db_session):
    ws, ceo, mgr, emp, project = await _world(db_session)
    now = datetime.now(timezone.utc)
    task = Task(workspace_id=ws.id, project_id=project.id, title="Vua cap nhat",
               status=TaskStatus.in_progress, percent=20, priority=TaskPriority.medium,
               created_by=ceo.id, created_at=now - timedelta(days=10))
    db_session.add(task)
    await db_session.flush()
    db_session.add(TaskUpdate(workspace_id=ws.id, task_id=task.id, author_id=ceo.id,
                              content="update", created_at=now - timedelta(days=1)))
    await db_session.commit()

    result = await analytics_service.get_project_health(db_session, ceo, project.id, now=now)
    assert result["stale"] == []
    assert result["risk"] == "low"


@pytest.mark.asyncio
async def test_employee_sees_project_health_via_visible_project_ids(db_session):
    """Đúng precedent snapshot_service (mục Dự án): 1 project vào visible_project_ids
    thì thấy AGGREGATE/DETAIL của CẢ project, không lọc tiếp theo visible_task_ids —
    vì project-level đã là 1 lớp quyền riêng (owner_id/assignee), không phải per-task."""
    ws, ceo, mgr, emp, project = await _world(db_session)
    my_task = Task(workspace_id=ws.id, project_id=project.id, title="Task cua emp",
                  status=TaskStatus.in_progress, percent=10, priority=TaskPriority.medium,
                  created_by=ceo.id)
    other_task = Task(workspace_id=ws.id, project_id=project.id, title="Task cua nguoi khac",
                     status=TaskStatus.blocked, percent=10, priority=TaskPriority.medium,
                     created_by=ceo.id)
    db_session.add_all([my_task, other_task])
    await db_session.flush()
    db_session.add(TaskAssignee(workspace_id=ws.id, task_id=my_task.id, user_id=emp.id))
    await db_session.commit()

    result = await analytics_service.get_project_health(db_session, emp, project.id)
    assert result["task_total"] == 2
