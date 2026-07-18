import pytest
from fastapi import HTTPException

from app.models import Project, Role, User, Workspace, WorkspacePlan
from app.services import report_schedule_service as svc
from app.tz import VN_TZ


_seq = iter(range(1000))


async def _setup(db, plan=WorkspacePlan.advanced):
    n = next(_seq)
    ws = Workspace(name=f"A{n}", plan=plan)
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email=f"c{n}@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    emp = User(workspace_id=ws.id, email=f"e{n}@a.vn", password_hash="x", full_name="E",
              role=Role.employee)
    db.add_all([ceo, emp])
    await db.flush()
    await db.commit()
    return ws, ceo, emp


@pytest.mark.asyncio
async def test_ceo_creates_schedule_with_correct_next_run_at(db_session):
    ws, ceo, emp = await _setup(db_session)
    sched = await svc.create_schedule(db_session, ceo, weekday=0, hour=8, minute=0)
    assert sched.workspace_id == ws.id
    assert sched.created_by == ceo.id
    assert sched.recipient_id == ceo.id  # mặc định = người tạo
    assert sched.active is True
    assert sched.next_run_at is not None
    # next_run_at lưu UTC — weekday/hour/minute CEO đặt là giờ VN, nên so sánh
    # phải convert ngược sang VN (giờ "now" thực tế lúc test chạy không cố định).
    next_run_vn = sched.next_run_at.astimezone(VN_TZ)
    assert next_run_vn.hour == 8 and next_run_vn.minute == 0
    assert next_run_vn.weekday() == 0


@pytest.mark.asyncio
async def test_employee_cannot_create_schedule(db_session):
    ws, ceo, emp = await _setup(db_session)
    with pytest.raises(HTTPException) as exc:
        await svc.create_schedule(db_session, emp, weekday=None, hour=8, minute=0)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_basic_plan_workspace_blocks_schedule_creation(db_session):
    ws, ceo, emp = await _setup(db_session, plan=WorkspacePlan.basic)
    with pytest.raises(HTTPException) as exc:
        await svc.create_schedule(db_session, ceo, weekday=None, hour=8, minute=0)
    assert exc.value.status_code == 403
    assert exc.value.detail == "advanced_plan_required"


@pytest.mark.asyncio
async def test_create_schedule_with_project_from_other_workspace_404s(db_session):
    ws, ceo, emp = await _setup(db_session)
    other_ws = Workspace(name="B", plan=WorkspacePlan.advanced)
    db_session.add(other_ws)
    await db_session.flush()
    other_ceo = User(workspace_id=other_ws.id, email="c2@b.vn", password_hash="x",
                     full_name="C2", role=Role.ceo, is_root=True)
    db_session.add(other_ceo)
    await db_session.flush()
    other_project = Project(workspace_id=other_ws.id, name="X", created_by=other_ceo.id)
    db_session.add(other_project)
    await db_session.flush()
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await svc.create_schedule(db_session, ceo, weekday=None, hour=8,
                                  project_id=other_project.id)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_recipient_can_be_someone_else_in_same_workspace(db_session):
    ws, ceo, emp = await _setup(db_session)
    sched = await svc.create_schedule(db_session, ceo, weekday=None, hour=8,
                                      recipient_id=emp.id)
    assert sched.recipient_id == emp.id


@pytest.mark.asyncio
async def test_list_schedules_scoped_to_workspace(db_session):
    ws, ceo, emp = await _setup(db_session)
    ws2, ceo2, _ = await _setup(db_session)
    await svc.create_schedule(db_session, ceo, weekday=None, hour=8)
    await svc.create_schedule(db_session, ceo2, weekday=None, hour=9)

    rows = await svc.list_schedules(db_session, ceo)
    assert len(rows) == 1
    assert rows[0].workspace_id == ws.id


@pytest.mark.asyncio
async def test_delete_schedule_removes_it_and_blocks_cross_workspace(db_session):
    ws, ceo, emp = await _setup(db_session)
    ws2, ceo2, _ = await _setup(db_session)
    sched = await svc.create_schedule(db_session, ceo, weekday=None, hour=8)

    with pytest.raises(HTTPException) as exc:
        await svc.delete_schedule(db_session, ceo2, sched.id)
    assert exc.value.status_code == 404

    await svc.delete_schedule(db_session, ceo, sched.id)
    rows = await svc.list_schedules(db_session, ceo)
    assert rows == []
