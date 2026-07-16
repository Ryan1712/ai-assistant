import pytest
from sqlalchemy import select

from app.models import AccountEvent, Project, Role, User, Workspace
from app.services import auth_service


async def _seed(db):
    """Workspace A: ceo root, mgr (co emp bao cao, so huu project), mgr2 (ung vien
    khoa/offboard/doi vai tro), emp (bao cao cho mgr)."""
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="ceo@a.vn", password_hash="x", full_name="Sep",
              role=Role.ceo, is_root=True)
    mgr = User(workspace_id=ws.id, email="mgr@a.vn", password_hash="x", full_name="Quan Ly",
              role=Role.manager)
    mgr2 = User(workspace_id=ws.id, email="mgr2@a.vn", password_hash="x", full_name="Quan Ly 2",
               role=Role.manager)
    db.add_all([ceo, mgr, mgr2])
    await db.flush()
    emp = User(workspace_id=ws.id, email="emp@a.vn", password_hash="x", full_name="Nhan Vien",
              role=Role.employee, manager_id=mgr.id)
    db.add(emp)
    await db.flush()
    project = Project(workspace_id=ws.id, name="Website", created_by=ceo.id, owner_id=mgr.id)
    db.add(project)
    await db.commit()
    return ws, ceo, mgr, mgr2, emp, project


async def _events_for(db, target_id):
    rows = await db.execute(select(AccountEvent).where(AccountEvent.target_user_id == target_id)
                            .order_by(AccountEvent.created_at.asc()))
    return list(rows.scalars())


@pytest.mark.asyncio
async def test_lock_user_writes_account_event(db_session):
    ws, ceo, mgr, mgr2, emp, project = await _seed(db_session)
    await auth_service.lock_user(db_session, ceo, mgr2.id)
    events = await _events_for(db_session, mgr2.id)
    assert len(events) == 1
    assert events[0].event_type == "locked"
    assert events[0].actor_id == ceo.id
    assert events[0].detail == "Khóa tài khoản"


@pytest.mark.asyncio
async def test_unlock_user_writes_account_event(db_session):
    ws, ceo, mgr, mgr2, emp, project = await _seed(db_session)
    await auth_service.lock_user(db_session, ceo, mgr2.id)
    await auth_service.unlock_user(db_session, ceo, mgr2.id)
    events = await _events_for(db_session, mgr2.id)
    assert [e.event_type for e in events] == ["locked", "unlocked"]


@pytest.mark.asyncio
async def test_offboard_user_writes_both_locked_and_offboarded_events(db_session):
    ws, ceo, mgr, mgr2, emp, project = await _seed(db_session)
    await auth_service.offboard_user(db_session, ceo, mgr2.id)
    events = await _events_for(db_session, mgr2.id)
    assert [e.event_type for e in events] == ["locked", "offboarded"]


@pytest.mark.asyncio
async def test_change_role_writes_account_event_for_role_change(db_session):
    ws, ceo, mgr, mgr2, emp, project = await _seed(db_session)
    await auth_service.change_role(db_session, ceo, emp.id, new_role=Role.manager)
    events = await _events_for(db_session, emp.id)
    assert len(events) == 1
    assert events[0].event_type == "role_changed"
    assert "role: employee -> manager" in events[0].detail


@pytest.mark.asyncio
async def test_change_role_writes_account_event_for_manager_only_change(db_session):
    ws, ceo, mgr, mgr2, emp, project = await _seed(db_session)
    await auth_service.change_role(db_session, ceo, emp.id, new_manager_id=mgr2.id)
    events = await _events_for(db_session, emp.id)
    assert len(events) == 1
    assert events[0].event_type == "role_changed"
    assert "manager_id" in events[0].detail
