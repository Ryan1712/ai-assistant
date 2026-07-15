import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models import Project, Role, Task, TaskAssignee, User, UserStatus, Workspace
from app.services import auth_service


async def _seed(db):
    """Workspace A: CEO root + manager (owner project, giao 1 task, co 1 direct report)
    + employee bao cao manager + successor (con hoat dong)."""
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="ceo@a.vn", password_hash="x", full_name="Sep",
              role=Role.ceo, is_root=True)
    mgr = User(workspace_id=ws.id, email="mgr@a.vn", password_hash="x", full_name="Quan Ly",
              role=Role.manager)
    successor = User(workspace_id=ws.id, email="ke-thua@a.vn", password_hash="x",
                     full_name="Nguoi Ke Thua", role=Role.manager)
    db.add_all([ceo, mgr, successor])
    await db.flush()
    emp = User(workspace_id=ws.id, email="emp@a.vn", password_hash="x", full_name="Nhan Vien",
              role=Role.employee, manager_id=mgr.id)
    db.add(emp)
    await db.flush()
    project = Project(workspace_id=ws.id, name="Website", created_by=ceo.id, owner_id=mgr.id)
    db.add(project)
    await db.flush()
    task = Task(workspace_id=ws.id, project_id=project.id, title="Sua loi", created_by=ceo.id)
    db.add(task)
    await db.flush()
    db.add(TaskAssignee(workspace_id=ws.id, task_id=task.id, user_id=mgr.id))
    await db.commit()
    return ws, ceo, mgr, emp, successor, project, task


@pytest.mark.asyncio
async def test_non_ceo_cannot_offboard(db_session):
    _, ceo, mgr, emp, successor, project, task = await _seed(db_session)
    with pytest.raises(HTTPException) as exc:
        await auth_service.offboard_user(db_session, emp, mgr.id)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_offboard_without_successor_only_locks(db_session):
    ws, ceo, mgr, emp, successor, project, task = await _seed(db_session)
    result = await auth_service.offboard_user(db_session, ceo, mgr.id)
    assert result == {"locked": True, "successor_id": None, "tasks_reassigned": 0,
                      "projects_reassigned": 0, "reports_reassigned": 0}
    await db_session.refresh(mgr)
    assert mgr.status == UserStatus.locked
    await db_session.refresh(project)
    assert project.owner_id == mgr.id


@pytest.mark.asyncio
async def test_offboard_with_successor_reassigns_everything(db_session):
    ws, ceo, mgr, emp, successor, project, task = await _seed(db_session)
    result = await auth_service.offboard_user(db_session, ceo, mgr.id, successor.id)
    assert result == {"locked": True, "successor_id": str(successor.id), "tasks_reassigned": 1,
                      "projects_reassigned": 1, "reports_reassigned": 1}

    await db_session.refresh(mgr)
    assert mgr.status == UserStatus.locked
    await db_session.refresh(project)
    assert project.owner_id == successor.id
    await db_session.refresh(emp)
    assert emp.manager_id == successor.id

    assignees = (await db_session.execute(
        select(TaskAssignee).where(TaskAssignee.task_id == task.id))).scalars().all()
    assert [a.user_id for a in assignees] == [successor.id]


@pytest.mark.asyncio
async def test_offboard_does_not_duplicate_existing_successor_assignment(db_session):
    ws, ceo, mgr, emp, successor, project, task = await _seed(db_session)
    db_session.add(TaskAssignee(workspace_id=ws.id, task_id=task.id, user_id=successor.id))
    await db_session.commit()

    result = await auth_service.offboard_user(db_session, ceo, mgr.id, successor.id)
    assert result["tasks_reassigned"] == 1

    assignees = (await db_session.execute(
        select(TaskAssignee).where(TaskAssignee.task_id == task.id))).scalars().all()
    assert [a.user_id for a in assignees] == [successor.id]


@pytest.mark.asyncio
async def test_successor_not_found_or_cross_workspace(db_session):
    ws, ceo, mgr, emp, successor, project, task = await _seed(db_session)
    other_ws = Workspace(name="B")
    db_session.add(other_ws)
    await db_session.flush()
    other_user = User(workspace_id=other_ws.id, email="other@b.vn", password_hash="x",
                      full_name="Khac Workspace", role=Role.manager)
    db_session.add(other_user)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await auth_service.offboard_user(db_session, ceo, mgr.id, other_user.id)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_successor_same_as_target_is_rejected(db_session):
    ws, ceo, mgr, emp, successor, project, task = await _seed(db_session)
    with pytest.raises(HTTPException) as exc:
        await auth_service.offboard_user(db_session, ceo, mgr.id, mgr.id)
    assert exc.value.status_code == 422
    assert exc.value.detail == "invalid_successor"


@pytest.mark.asyncio
async def test_locked_successor_is_rejected(db_session):
    ws, ceo, mgr, emp, successor, project, task = await _seed(db_session)
    successor.status = UserStatus.locked
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await auth_service.offboard_user(db_session, ceo, mgr.id, successor.id)
    assert exc.value.status_code == 422
    assert exc.value.detail == "invalid_successor"


@pytest.mark.asyncio
async def test_root_ceo_cannot_be_offboarded(db_session):
    ws, ceo, mgr, emp, successor, project, task = await _seed(db_session)
    with pytest.raises(HTTPException) as exc:
        await auth_service.offboard_user(db_session, ceo, ceo.id)
    assert exc.value.status_code == 403
    assert exc.value.detail == "cannot_lock_root_ceo"


@pytest.mark.asyncio
async def test_non_root_ceo_cannot_offboard_another_ceo(db_session):
    ws, ceo, mgr, emp, successor, project, task = await _seed(db_session)
    ceo2 = User(workspace_id=ws.id, email="ceo2@a.vn", password_hash="x", full_name="CEO 2",
               role=Role.ceo, is_root=False)
    ceo3 = User(workspace_id=ws.id, email="ceo3@a.vn", password_hash="x", full_name="CEO 3",
               role=Role.ceo, is_root=False)
    db_session.add_all([ceo2, ceo3])
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await auth_service.offboard_user(db_session, ceo2, ceo3.id)
    assert exc.value.status_code == 403
    assert exc.value.detail == "only_root_can_lock_ceo"


@pytest.mark.asyncio
async def test_offboard_is_idempotent_on_already_locked_user(db_session):
    ws, ceo, mgr, emp, successor, project, task = await _seed(db_session)
    await auth_service.offboard_user(db_session, ceo, mgr.id)
    result = await auth_service.offboard_user(db_session, ceo, mgr.id, successor.id)
    assert result["tasks_reassigned"] == 1


@pytest.mark.asyncio
async def test_successor_who_is_own_direct_report_does_not_become_self_managed(db_session):
    ws, ceo, mgr, emp, successor, project, task = await _seed(db_session)
    successor.manager_id = mgr.id  # successor la 1 direct report cua chinh mgr
    await db_session.commit()

    result = await auth_service.offboard_user(db_session, ceo, mgr.id, successor.id)

    await db_session.refresh(successor)
    assert successor.manager_id != successor.id
    assert successor.manager_id == mgr.id  # khong bi doi vi successor bi loai khoi phep gan lai
    # emp (direct report khac) van duoc chuyen sang successor binh thuong
    assert result["reports_reassigned"] == 1
