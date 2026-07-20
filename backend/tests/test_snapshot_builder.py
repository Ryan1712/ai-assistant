"""Phase 1: builder SQL aggregates — thuần data, chưa render/chưa quyền."""
import uuid
from datetime import datetime, timedelta, timezone

from app.models import (
    Project, Role, Task, TaskAssignee, TaskStatus, TaskUpdate, User, Workspace,
)
from app.services.snapshot_service import build_workspace_data

NOW = datetime(2026, 7, 20, 3, 0, tzinfo=timezone.utc)  # 10:00 giờ VN 20/07


async def _world(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x",
               full_name="Sếp", role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    ha = User(workspace_id=ws.id, email="ha@a.vn", password_hash="x",
              full_name="Hà Trần", role=Role.manager)
    db.add(ha)
    await db.flush()
    duy = User(workspace_id=ws.id, email="duy@a.vn", password_hash="x",
               full_name="Duy Phạm", role=Role.employee, manager_id=ha.id)
    db.add(duy)
    await db.flush()
    p = Project(workspace_id=ws.id, name="Marketing Q3", created_by=ceo.id)
    db.add(p)
    await db.flush()
    t1 = Task(workspace_id=ws.id, project_id=p.id, title="Landing page",
              status=TaskStatus.in_progress, percent=40,
              deadline=NOW + timedelta(days=3), created_by=ceo.id)
    t2 = Task(workspace_id=ws.id, project_id=p.id, title="Báo cáo thuế",
              status=TaskStatus.todo, percent=0,
              deadline=NOW - timedelta(days=2), created_by=ceo.id)   # quá hạn
    t3 = Task(workspace_id=ws.id, project_id=p.id, title="Việc xong",
              status=TaskStatus.done, percent=100, created_by=ceo.id)
    t4 = Task(workspace_id=ws.id, project_id=p.id, title="Họp khách",
              status=TaskStatus.todo, percent=0,
              deadline=NOW + timedelta(hours=2), created_by=ceo.id)  # đến hạn hôm nay (VN)
    db.add_all([t1, t2, t3, t4])
    await db.flush()
    db.add_all([
        TaskAssignee(workspace_id=ws.id, task_id=t1.id, user_id=duy.id),
        TaskAssignee(workspace_id=ws.id, task_id=t2.id, user_id=duy.id),
        TaskAssignee(workspace_id=ws.id, task_id=t4.id, user_id=ha.id),
    ])
    db.add(TaskUpdate(workspace_id=ws.id, task_id=t1.id, author_id=duy.id,
                      content="đã xong hero section", percent=40,
                      created_at=NOW - timedelta(hours=2)))
    await db.commit()
    return ws, ceo, ha, duy, p, (t1, t2, t3, t4)


async def test_project_aggregates(db_session):
    ws, *_ = await _world(db_session)
    data = await build_workspace_data(db_session, ws.id, now=NOW)
    (proj,) = data["projects"]
    assert proj["name"] == "Marketing Q3"
    assert proj["task_total"] == 4
    assert proj["task_open"] == 3
    assert proj["task_overdue"] == 1
    assert proj["task_done"] == 1
    assert proj["percent_avg"] == 35   # (40+0+100+0)/4
    assert isinstance(proj["id"], str)


async def test_user_workload_va_doing(db_session):
    ws, ceo, ha, duy, p, tasks = await _world(db_session)
    data = await build_workspace_data(db_session, ws.id, now=NOW)
    by_name = {u["full_name"]: u for u in data["users"]}
    assert by_name["Duy Phạm"]["open_count"] == 2
    assert by_name["Duy Phạm"]["overdue_count"] == 1
    assert by_name["Duy Phạm"]["manager_name"] == "Hà Trần"
    assert by_name["Duy Phạm"]["doing"][0]["title"] == "Landing page"
    assert by_name["Duy Phạm"]["doing"][0]["percent"] == 40
    assert by_name["Duy Phạm"]["last_update_at"] is not None
    assert by_name["Hà Trần"]["open_count"] == 1
    assert by_name["Sếp"]["open_count"] == 0


async def test_today_va_updates(db_session):
    ws, *_ = await _world(db_session)
    data = await build_workspace_data(db_session, ws.id, now=NOW)
    assert [t["title"] for t in data["due_today"]] == ["Họp khách"]
    assert data["due_today"][0]["assignees"] == ["Hà Trần"]
    assert [t["title"] for t in data["overdue"]] == ["Báo cáo thuế"]
    (upd,) = data["updates_24h"]
    assert upd["author"] == "Duy Phạm"
    assert upd["task_title"] == "Landing page"
    assert upd["percent"] == 40


async def test_workspace_khac_khong_lan(db_session):
    ws, *_ = await _world(db_session)
    ws2 = Workspace(name="B")
    db_session.add(ws2)
    await db_session.flush()
    u2 = User(workspace_id=ws2.id, email="x@b.vn", password_hash="x",
              full_name="Người B", role=Role.ceo)
    db_session.add(u2)
    await db_session.commit()
    data = await build_workspace_data(db_session, ws2.id, now=NOW)
    assert data["projects"] == []
    assert [u["full_name"] for u in data["users"]] == ["Người B"]
    assert data["due_today"] == [] and data["overdue"] == [] and data["updates_24h"] == []
