from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.models import Project, Role, Task, TaskAssignee, TaskPriority, TaskStatus, TaskUpdate, User, Workspace
from app.services import analytics_service
from app.tz import VN_TZ

# Cột DB timezone=True nhưng SQLite (test) chỉ round-trip đúng giờ khi giá trị ghi
# vào LÀ UTC (invariant y hệt _now() trong models.py — xem comment ở dashboard_service/
# snapshot_service/voice_service). Định nghĩa mốc theo giờ VN cho dễ đọc rồi đổi
# sang UTC ngay trước khi dùng, tránh SQLite trả naive rồi bị đọc nhầm 7 tiếng.
MON_2024_01_01 = datetime(2024, 1, 1, 0, 5, tzinfo=VN_TZ).astimezone(timezone.utc)  # đầu tuần (thứ 2)
SUN_2023_12_31 = datetime(2023, 12, 31, 23, 55, tzinfo=VN_TZ).astimezone(timezone.utc)  # cuối tuần trước
FIRST_OF_MONTH = datetime(2024, 2, 1, 0, 5, tzinfo=VN_TZ).astimezone(timezone.utc)
LAST_OF_PREV_MONTH = datetime(2024, 1, 31, 23, 55, tzinfo=VN_TZ).astimezone(timezone.utc)


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
async def test_invalid_period_422(db_session):
    ws, ceo, mgr, emp, project = await _world(db_session)
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await analytics_service.get_progress_stats(db_session, ceo, period="quarter")
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_no_tasks_in_scope_has_note(db_session):
    ws, ceo, mgr, emp, project = await _world(db_session)
    await db_session.commit()
    result = await analytics_service.get_progress_stats(db_session, ceo, period="week")
    assert result["current"] == {"completed": 0, "created": 0, "overdue": 0}
    assert result.get("note")


@pytest.mark.asyncio
async def test_week_boundary_monday_vs_last_sunday(db_session):
    ws, ceo, mgr, emp, project = await _world(db_session)
    this_week_task = Task(workspace_id=ws.id, project_id=project.id, title="Tuan nay",
                          status=TaskStatus.todo, percent=0, priority=TaskPriority.medium,
                          created_by=ceo.id, created_at=MON_2024_01_01)
    last_week_task = Task(workspace_id=ws.id, project_id=project.id, title="Tuan truoc",
                          status=TaskStatus.todo, percent=0, priority=TaskPriority.medium,
                          created_by=ceo.id, created_at=SUN_2023_12_31)
    db_session.add_all([this_week_task, last_week_task])
    await db_session.commit()

    result = await analytics_service.get_progress_stats(
        db_session, ceo, period="week", now=MON_2024_01_01)
    assert result["current"]["created"] == 1
    assert result["previous"]["created"] == 1
    assert result["change"]["created_diff"] == 0


@pytest.mark.asyncio
async def test_month_boundary_first_vs_last_day_prev_month(db_session):
    ws, ceo, mgr, emp, project = await _world(db_session)
    this_month_task = Task(workspace_id=ws.id, project_id=project.id, title="Thang nay",
                           status=TaskStatus.todo, percent=0, priority=TaskPriority.medium,
                           created_by=ceo.id, created_at=FIRST_OF_MONTH)
    last_month_task = Task(workspace_id=ws.id, project_id=project.id, title="Thang truoc",
                           status=TaskStatus.todo, percent=0, priority=TaskPriority.medium,
                           created_by=ceo.id, created_at=LAST_OF_PREV_MONTH)
    db_session.add_all([this_month_task, last_month_task])
    await db_session.commit()

    result = await analytics_service.get_progress_stats(
        db_session, ceo, period="month", now=FIRST_OF_MONTH)
    assert result["current"]["created"] == 1
    assert result["previous"]["created"] == 1


@pytest.mark.asyncio
async def test_completed_counts_from_task_updates_current_vs_previous(db_session):
    ws, ceo, mgr, emp, project = await _world(db_session)
    t1 = Task(workspace_id=ws.id, project_id=project.id, title="Xong tuan nay",
             status=TaskStatus.done, percent=100, priority=TaskPriority.medium,
             created_by=ceo.id, created_at=SUN_2023_12_31)
    t2 = Task(workspace_id=ws.id, project_id=project.id, title="Xong tuan truoc",
             status=TaskStatus.done, percent=100, priority=TaskPriority.medium,
             created_by=ceo.id, created_at=SUN_2023_12_31)
    db_session.add_all([t1, t2])
    await db_session.flush()
    db_session.add_all([
        TaskUpdate(workspace_id=ws.id, task_id=t1.id, author_id=ceo.id, status=TaskStatus.done,
                  created_at=MON_2024_01_01),
        TaskUpdate(workspace_id=ws.id, task_id=t2.id, author_id=ceo.id, status=TaskStatus.done,
                  created_at=SUN_2023_12_31),
    ])
    await db_session.commit()

    result = await analytics_service.get_progress_stats(
        db_session, ceo, period="week", now=MON_2024_01_01)
    assert result["current"]["completed"] == 1
    assert result["previous"]["completed"] == 1
    assert result["change"]["completed_diff"] == 0


@pytest.mark.asyncio
async def test_overdue_now_counts_open_tasks_past_deadline(db_session):
    ws, ceo, mgr, emp, project = await _world(db_session)
    now = MON_2024_01_01
    overdue_task = Task(workspace_id=ws.id, project_id=project.id, title="Tre han",
                        status=TaskStatus.in_progress, percent=10, priority=TaskPriority.medium,
                        created_by=ceo.id, deadline=now - timedelta(days=2))
    db_session.add(overdue_task)
    await db_session.commit()

    result = await analytics_service.get_progress_stats(db_session, ceo, period="week", now=now)
    assert result["current"]["overdue"] == 1


@pytest.mark.asyncio
async def test_project_scope_restricts_to_project_tasks(db_session):
    ws, ceo, mgr, emp, project = await _world(db_session)
    other_project = Project(workspace_id=ws.id, name="Du an Y", created_by=ceo.id)
    db_session.add(other_project)
    await db_session.flush()
    in_scope = Task(workspace_id=ws.id, project_id=project.id, title="Trong pham vi",
                    status=TaskStatus.todo, percent=0, priority=TaskPriority.medium,
                    created_by=ceo.id, created_at=MON_2024_01_01)
    out_scope = Task(workspace_id=ws.id, project_id=other_project.id, title="Ngoai pham vi",
                     status=TaskStatus.todo, percent=0, priority=TaskPriority.medium,
                     created_by=ceo.id, created_at=MON_2024_01_01)
    db_session.add_all([in_scope, out_scope])
    await db_session.commit()

    result = await analytics_service.get_progress_stats(
        db_session, ceo, period="week", project_id=project.id, now=MON_2024_01_01)
    assert result["current"]["created"] == 1


@pytest.mark.asyncio
async def test_project_scope_not_visible_404(db_session):
    ws, ceo, mgr, emp, project = await _world(db_session)
    ws2 = Workspace(name="B")
    db_session.add(ws2)
    await db_session.flush()
    outsider = User(workspace_id=ws2.id, email="x@b.vn", password_hash="x", full_name="X",
                    role=Role.ceo, is_root=True)
    db_session.add(outsider)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await analytics_service.get_progress_stats(db_session, outsider, period="week",
                                                    project_id=project.id)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_employee_scope_limited_to_visible_task_ids_when_no_project(db_session):
    ws, ceo, mgr, emp, project = await _world(db_session)
    my_task = Task(workspace_id=ws.id, project_id=project.id, title="Task cua emp",
                  status=TaskStatus.todo, percent=0, priority=TaskPriority.medium,
                  created_by=ceo.id, created_at=MON_2024_01_01)
    other_task = Task(workspace_id=ws.id, project_id=project.id, title="Task cua nguoi khac",
                     status=TaskStatus.todo, percent=0, priority=TaskPriority.medium,
                     created_by=ceo.id, created_at=MON_2024_01_01)
    db_session.add_all([my_task, other_task])
    await db_session.flush()
    db_session.add(TaskAssignee(workspace_id=ws.id, task_id=my_task.id, user_id=emp.id))
    await db_session.commit()

    result = await analytics_service.get_progress_stats(
        db_session, emp, period="week", now=MON_2024_01_01)
    assert result["current"]["created"] == 1
