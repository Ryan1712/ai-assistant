import pytest

from app.models import Role, User, Workspace
from app.permissions import can_assign_directive


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
    duy = User(workspace_id=ws.id, email="d@a.vn", password_hash="x", full_name="Duy",
              role=Role.employee, manager_id=mgr.id)
    other_mgr = User(workspace_id=ws.id, email="m2@a.vn", password_hash="x", full_name="M2",
                     role=Role.manager)
    db.add_all([duy, other_mgr])
    await db.flush()
    nam = User(workspace_id=ws.id, email="n@a.vn", password_hash="x", full_name="Nam",
              role=Role.employee, manager_id=other_mgr.id)
    db.add(nam)
    await db.flush()
    await db.commit()
    return ws, ceo, mgr, duy, other_mgr, nam


@pytest.mark.asyncio
async def test_ceo_can_assign_directive_to_anyone(db_session):
    ws, ceo, mgr, duy, other_mgr, nam = await _world(db_session)
    assert await can_assign_directive(db_session, ceo, duy.id) is True
    assert await can_assign_directive(db_session, ceo, nam.id) is True
    assert await can_assign_directive(db_session, ceo, mgr.id) is True


@pytest.mark.asyncio
async def test_manager_can_assign_directive_to_own_direct_report(db_session):
    ws, ceo, mgr, duy, other_mgr, nam = await _world(db_session)
    assert await can_assign_directive(db_session, mgr, duy.id) is True


@pytest.mark.asyncio
async def test_manager_cannot_assign_directive_to_other_managers_report(db_session):
    ws, ceo, mgr, duy, other_mgr, nam = await _world(db_session)
    assert await can_assign_directive(db_session, mgr, nam.id) is False


@pytest.mark.asyncio
async def test_manager_cannot_assign_directive_to_self_or_peer_manager(db_session):
    ws, ceo, mgr, duy, other_mgr, nam = await _world(db_session)
    assert await can_assign_directive(db_session, mgr, mgr.id) is False
    assert await can_assign_directive(db_session, mgr, other_mgr.id) is False


@pytest.mark.asyncio
async def test_employee_cannot_assign_directive_to_anyone(db_session):
    ws, ceo, mgr, duy, other_mgr, nam = await _world(db_session)
    assert await can_assign_directive(db_session, duy, nam.id) is False
    assert await can_assign_directive(db_session, duy, ceo.id) is False
