import pytest

from app.agent.tools import TOOLS, call_tool
from app.models import LoginEvent, Role, User, Workspace
from app.services import audit_service


async def _world(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    emp = User(workspace_id=ws.id, email="e@a.vn", password_hash="x", full_name="E",
              role=Role.employee)
    db.add_all([ceo, emp])
    await db.commit()
    return ws, ceo, emp


def test_list_audit_events_tool_registered_and_not_sensitive():
    spec = TOOLS["list_audit_events"]
    assert spec.sensitive is False


@pytest.mark.asyncio
async def test_list_audit_events_returns_events(db_session):
    ws, ceo, emp = await _world(db_session)
    db_session.add(LoginEvent(workspace_id=ws.id, user_id=emp.id, device_uuid="d1",
                              device_name="iPhone"))
    await db_session.commit()

    got = await call_tool(db_session, ceo, "list_audit_events", {})
    assert len(got["events"]) == 1
    assert got["events"][0]["type"] == "login"


@pytest.mark.asyncio
async def test_list_audit_events_non_ceo_gets_forbidden_error(db_session):
    ws, ceo, emp = await _world(db_session)
    got = await call_tool(db_session, emp, "list_audit_events", {})
    assert got["error"] == "forbidden"
