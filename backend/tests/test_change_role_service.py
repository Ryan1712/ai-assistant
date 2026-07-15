import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models import Project, Role, Task, TaskAssignee, User, UserStatus, Workspace
from app.services import auth_service


async def _seed(db):
    """Workspace A: root CEO + mgr (manager, co 1 direct report emp + so huu 1 project)
    + mgr2 (manager khac, ung vien lam new_manager_id/successor) + ceo2 (CEO khong root)."""
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="ceo@a.vn", password_hash="x", full_name="Sep",
              role=Role.ceo, is_root=True)
    mgr = User(workspace_id=ws.id, email="mgr@a.vn", password_hash="x", full_name="Quan Ly",
              role=Role.manager)
    mgr2 = User(workspace_id=ws.id, email="mgr2@a.vn", password_hash="x", full_name="Quan Ly 2",
               role=Role.manager)
    ceo2 = User(workspace_id=ws.id, email="ceo2@a.vn", password_hash="x", full_name="CEO 2",
               role=Role.ceo, is_root=False)
    db.add_all([ceo, mgr, mgr2, ceo2])
    await db.flush()
    emp = User(workspace_id=ws.id, email="emp@a.vn", password_hash="x", full_name="Nhan Vien",
              role=Role.employee, manager_id=mgr.id)
    db.add(emp)
    await db.flush()
    project = Project(workspace_id=ws.id, name="Website", created_by=ceo.id, owner_id=mgr.id)
    db.add(project)
    await db.commit()
    return ws, ceo, mgr, mgr2, emp, ceo2, project


@pytest.mark.asyncio
async def test_non_ceo_cannot_change_role(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    with pytest.raises(HTTPException) as exc:
        await auth_service.change_role(db_session, emp, mgr2.id, new_role=Role.employee)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_promote_employee_to_manager(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    result = await auth_service.change_role(db_session, ceo, emp.id, new_role=Role.manager)
    assert result["role"] == "manager"
    assert result["reports_reassigned"] == 0
    assert result["projects_reassigned"] == 0
    await db_session.refresh(emp)
    assert emp.role == Role.manager


@pytest.mark.asyncio
async def test_change_manager_only(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    result = await auth_service.change_role(db_session, ceo, emp.id, new_manager_id=mgr2.id)
    assert result["role"] == "employee"
    assert result["manager_id"] == str(mgr2.id)
    await db_session.refresh(emp)
    assert emp.manager_id == mgr2.id
    assert emp.role == Role.employee


@pytest.mark.asyncio
async def test_demote_manager_with_dependents_requires_successor(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    with pytest.raises(HTTPException) as exc:
        await auth_service.change_role(db_session, ceo, mgr.id, new_role=Role.employee,
                                       new_manager_id=mgr2.id)
    assert exc.value.status_code == 422
    assert exc.value.detail == "successor_required"


@pytest.mark.asyncio
async def test_demote_manager_new_manager_and_successor_are_independent(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    mgr3 = User(workspace_id=ws.id, email="mgr3@a.vn", password_hash="x", full_name="Quan Ly 3",
               role=Role.manager)
    db_session.add(mgr3)
    await db_session.commit()

    result = await auth_service.change_role(db_session, ceo, mgr.id, new_role=Role.employee,
                                            new_manager_id=mgr3.id, successor_id=mgr2.id)
    assert result["manager_id"] == str(mgr3.id)
    assert result["successor_id"] == str(mgr2.id)
    assert result["reports_reassigned"] == 1
    assert result["projects_reassigned"] == 1
    await db_session.refresh(mgr)
    assert mgr.manager_id == mgr3.id
    await db_session.refresh(emp)
    assert emp.manager_id == mgr2.id
    await db_session.refresh(project)
    assert project.owner_id == mgr2.id


@pytest.mark.asyncio
async def test_demote_manager_keeps_own_task_assignments(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    task = Task(workspace_id=ws.id, project_id=project.id, title="Sua loi", created_by=ceo.id)
    db_session.add(task)
    await db_session.flush()
    db_session.add(TaskAssignee(workspace_id=ws.id, task_id=task.id, user_id=mgr.id))
    await db_session.commit()

    await auth_service.change_role(db_session, ceo, mgr.id, new_role=Role.employee,
                                   new_manager_id=mgr2.id, successor_id=mgr2.id)

    assignees = (await db_session.execute(
        select(TaskAssignee).where(TaskAssignee.task_id == task.id))).scalars().all()
    assert [a.user_id for a in assignees] == [mgr.id]


@pytest.mark.asyncio
async def test_leaving_manager_without_dependents_no_successor_needed(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    result = await auth_service.change_role(db_session, ceo, mgr2.id, new_role=Role.employee,
                                            new_manager_id=mgr.id)
    assert result["reports_reassigned"] == 0
    assert result["projects_reassigned"] == 0


@pytest.mark.asyncio
async def test_employee_role_without_any_manager_rejected(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    with pytest.raises(HTTPException) as exc:
        await auth_service.change_role(db_session, ceo, ceo2.id, new_role=Role.employee)
    assert exc.value.status_code == 422
    assert exc.value.detail == "employee_requires_manager"


@pytest.mark.asyncio
async def test_new_manager_must_have_manager_role(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    with pytest.raises(HTTPException) as exc:
        await auth_service.change_role(db_session, ceo, emp.id, new_manager_id=ceo2.id)
    assert exc.value.status_code == 422
    assert exc.value.detail == "invalid_manager"


@pytest.mark.asyncio
async def test_new_manager_cannot_be_self(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    with pytest.raises(HTTPException) as exc:
        await auth_service.change_role(db_session, ceo, mgr.id, new_manager_id=mgr.id)
    assert exc.value.status_code == 422
    assert exc.value.detail == "invalid_manager"


@pytest.mark.asyncio
async def test_no_change_requested(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    with pytest.raises(HTTPException) as exc:
        await auth_service.change_role(db_session, ceo, mgr.id)
    assert exc.value.status_code == 422
    assert exc.value.detail == "no_change_requested"


@pytest.mark.asyncio
async def test_root_ceo_role_is_immutable(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    with pytest.raises(HTTPException) as exc:
        await auth_service.change_role(db_session, ceo, ceo.id, new_role=Role.manager)
    assert exc.value.status_code == 403
    assert exc.value.detail == "cannot_change_root_ceo"


@pytest.mark.asyncio
async def test_non_root_ceo_cannot_change_another_ceo(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    ceo3 = User(workspace_id=ws.id, email="ceo3@a.vn", password_hash="x", full_name="CEO 3",
               role=Role.ceo, is_root=False)
    db_session.add(ceo3)
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await auth_service.change_role(db_session, ceo2, ceo3.id, new_role=Role.manager)
    assert exc.value.status_code == 403
    assert exc.value.detail == "only_root_can_change_ceo"


@pytest.mark.asyncio
async def test_non_root_ceo_cannot_promote_employee_to_ceo(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    with pytest.raises(HTTPException) as exc:
        await auth_service.change_role(db_session, ceo2, emp.id, new_role=Role.ceo)
    assert exc.value.status_code == 403
    assert exc.value.detail == "only_root_can_change_ceo"


@pytest.mark.asyncio
async def test_root_ceo_can_promote_employee_to_ceo(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    result = await auth_service.change_role(db_session, ceo, mgr2.id, new_role=Role.ceo)
    assert result["role"] == "ceo"
    await db_session.refresh(mgr2)
    assert mgr2.role == Role.ceo


@pytest.mark.asyncio
async def test_successor_not_found_or_cross_workspace(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    other_ws = Workspace(name="B")
    db_session.add(other_ws)
    await db_session.flush()
    other_user = User(workspace_id=other_ws.id, email="other@b.vn", password_hash="x",
                      full_name="Khac Workspace", role=Role.manager)
    db_session.add(other_user)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await auth_service.change_role(db_session, ceo, mgr.id, new_role=Role.employee,
                                       new_manager_id=mgr2.id, successor_id=other_user.id)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_successor_same_as_target_rejected(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    with pytest.raises(HTTPException) as exc:
        await auth_service.change_role(db_session, ceo, mgr.id, new_role=Role.employee,
                                       new_manager_id=mgr2.id, successor_id=mgr.id)
    assert exc.value.status_code == 422
    assert exc.value.detail == "invalid_successor"


@pytest.mark.asyncio
async def test_locked_successor_rejected(db_session):
    ws, ceo, mgr, mgr2, emp, ceo2, project = await _seed(db_session)
    mgr2.status = UserStatus.locked
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await auth_service.change_role(db_session, ceo, mgr.id, new_role=Role.employee,
                                       new_manager_id=mgr2.id, successor_id=mgr2.id)
    assert exc.value.status_code == 422
    assert exc.value.detail == "invalid_successor"
