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
    assert SENSITIVE_TOOLS == {"lock_user", "unlock_user", "delete_instruction", "send_email",
                               "offboard_user"}
    assert TOOLS["create_invite"].sensitive is False


@pytest.mark.asyncio
async def test_list_users_tool_is_company_directory_for_everyone(db_session):
    """E2E 2026-07-13: agent bí user_id (giao việc/gửi email/khóa) vì không có tool
    danh bạ. list_users = danh bạ công ty — MỌI vai trò thấy đủ thành viên workspace
    mình (như member list Slack); quyền HÀNH ĐỘNG vẫn chặn ở service layer."""
    ws, ceo = await _ceo(db_session)
    emp = User(workspace_id=ws.id, email="e@a.vn", password_hash="x", full_name="E",
              role=Role.employee)
    ws2 = Workspace(name="B")
    db_session.add_all([emp, ws2])
    await db_session.flush()
    outsider = User(workspace_id=ws2.id, email="x@b.vn", password_hash="x", full_name="X",
                   role=Role.ceo, is_root=True)
    db_session.add(outsider)
    await db_session.flush()
    await db_session.commit()

    result = await call_tool(db_session, emp, "list_users", {})
    emails = {u["email"] for u in result["users"]}
    assert emails == {"c@a.vn", "e@a.vn"}  # thấy CEO, không thấy workspace khác
    u = next(u for u in result["users"] if u["email"] == "c@a.vn")
    assert u["role"] == "ceo" and u["full_name"] == "C" and "id" in u
    assert TOOLS["list_users"].sensitive is False
