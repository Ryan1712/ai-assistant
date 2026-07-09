import pytest

from app.agent.tools import SENSITIVE_TOOLS, TOOLS, call_tool
from app.models import Role, User, UserStatus, Workspace


async def _ceo(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    return ws, ceo


@pytest.mark.asyncio
async def test_create_invite_tool(db_session):
    ws, ceo = await _ceo(db_session)
    result = await call_tool(db_session, ceo, "create_invite", {"role": "manager"})
    assert result["role"] == "manager"
    assert "token" in result


@pytest.mark.asyncio
async def test_lock_and_unlock_user_tools(db_session):
    ws, ceo = await _ceo(db_session)
    emp = User(workspace_id=ws.id, email="e@a.vn", password_hash="x", full_name="E",
              role=Role.employee)
    db_session.add(emp)
    await db_session.flush()
    await db_session.commit()

    locked = await call_tool(db_session, ceo, "lock_user", {"target_id": str(emp.id)})
    assert locked == {"user_id": str(emp.id), "locked": True}
    await db_session.refresh(emp)
    assert emp.status == UserStatus.locked

    unlocked = await call_tool(db_session, ceo, "unlock_user", {"target_id": str(emp.id)})
    assert unlocked == {"user_id": str(emp.id), "locked": False}


@pytest.mark.asyncio
async def test_lock_root_ceo_tool_is_forbidden(db_session):
    ws, ceo = await _ceo(db_session)
    result = await call_tool(db_session, ceo, "lock_user", {"target_id": str(ceo.id)})
    assert result["error"] == "forbidden"


def test_lock_and_unlock_are_marked_sensitive():
    assert SENSITIVE_TOOLS == {"lock_user", "unlock_user"}
    assert TOOLS["create_invite"].sensitive is False
