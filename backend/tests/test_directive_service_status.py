import pytest

from app.models import Directive, Role, User, Workspace
from app.services import directive_service


async def _world(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    mgr = User(workspace_id=ws.id, email="m@a.vn", password_hash="x", full_name="Ha",
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
    # directive tu CEO giao cho Nam (khong lien quan mgr)
    d_ceo_to_nam = Directive(workspace_id=ws.id, created_by=ceo.id, recipient_id=nam.id,
                             verbatim_text="x")
    # directive tu mgr giao cho Duy (direct report cua mgr)
    d_mgr_to_duy = Directive(workspace_id=ws.id, created_by=mgr.id, recipient_id=duy.id,
                             verbatim_text="y")
    db.add_all([d_ceo_to_nam, d_mgr_to_duy])
    await db.commit()
    return ws, ceo, mgr, duy, other_mgr, nam, d_ceo_to_nam, d_mgr_to_duy


@pytest.mark.asyncio
async def test_ceo_sees_all_directives_in_workspace(db_session):
    ws, ceo, mgr, duy, other_mgr, nam, d1, d2 = await _world(db_session)
    result = await directive_service.get_directive_status(db_session, ceo)
    assert {d["id"] for d in result["directives"]} == {str(d1.id), str(d2.id)}


@pytest.mark.asyncio
async def test_manager_sees_own_created_and_own_reports_received(db_session):
    ws, ceo, mgr, duy, other_mgr, nam, d1, d2 = await _world(db_session)
    result = await directive_service.get_directive_status(db_session, mgr)
    assert {d["id"] for d in result["directives"]} == {str(d2.id)}


@pytest.mark.asyncio
async def test_employee_sees_only_own_received(db_session):
    ws, ceo, mgr, duy, other_mgr, nam, d1, d2 = await _world(db_session)
    result = await directive_service.get_directive_status(db_session, duy)
    assert {d["id"] for d in result["directives"]} == {str(d2.id)}


@pytest.mark.asyncio
async def test_empty_result_has_note(db_session):
    ws, ceo, mgr, duy, other_mgr, nam, d1, d2 = await _world(db_session)
    ws2 = Workspace(name="B")
    db_session.add(ws2)
    await db_session.flush()
    lonely_mgr = User(workspace_id=ws2.id, email="lonely@a.vn", password_hash="x",
                      full_name="Lonely", role=Role.manager)
    db_session.add(lonely_mgr)
    await db_session.commit()

    result = await directive_service.get_directive_status(db_session, lonely_mgr)
    assert result["directives"] == []
    assert result.get("note")
