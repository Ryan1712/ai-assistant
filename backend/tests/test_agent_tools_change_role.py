import pytest

from app.agent.tools import TOOLS, call_tool
from app.models import Role, User, Workspace


async def _seed(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    mgr = User(workspace_id=ws.id, email="m@a.vn", password_hash="x", full_name="M",
              role=Role.manager)
    db.add_all([ceo, mgr])
    await db.flush()
    await db.commit()
    return ws, ceo, mgr


def test_change_user_role_tool_registered_and_sensitive():
    assert "change_user_role" in TOOLS
    assert TOOLS["change_user_role"].sensitive is True
    assert len(TOOLS) == 45  # +list_notifications, list_reports (2026-07-17)


@pytest.mark.asyncio
async def test_change_user_role_tool_updates_manager(db_session):
    ws, ceo, mgr = await _seed(db_session)
    employee = User(workspace_id=ws.id, email="e@a.vn", password_hash="x", full_name="E",
                    role=Role.employee, manager_id=mgr.id)
    mgr2 = User(workspace_id=ws.id, email="m2@a.vn", password_hash="x", full_name="M2",
               role=Role.manager)
    db_session.add_all([employee, mgr2])
    await db_session.commit()

    result = await call_tool(db_session, ceo, "change_user_role",
                             {"user_id": str(employee.id), "new_manager_id": str(mgr2.id)})
    assert result["manager_id"] == str(mgr2.id)


@pytest.mark.asyncio
async def test_change_user_role_tool_wraps_forbidden_error(db_session):
    ws, ceo, mgr = await _seed(db_session)
    employee = User(workspace_id=ws.id, email="e@a.vn", password_hash="x", full_name="E",
                    role=Role.employee, manager_id=mgr.id)
    db_session.add(employee)
    await db_session.commit()

    result = await call_tool(db_session, employee, "change_user_role",
                             {"user_id": str(mgr.id), "new_role": "employee"})
    assert result["error"] == "forbidden"
