import pytest

from app.agent.tools import TOOLS, call_tool
from app.models import Role, User, Workspace


async def _ceo(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    successor = User(workspace_id=ws.id, email="ke-thua@a.vn", password_hash="x",
                     full_name="Ke Thua", role=Role.manager)
    target = User(workspace_id=ws.id, email="target@a.vn", password_hash="x",
                  full_name="Nguoi Nghi", role=Role.manager)
    db.add_all([successor, target])
    await db.flush()
    await db.commit()
    return ws, ceo, successor, target


def test_offboard_user_tool_registered_and_sensitive():
    assert "offboard_user" in TOOLS
    assert TOOLS["offboard_user"].sensitive is True
    assert len(TOOLS) == 41  # +change_user_role (2026-07-15)


@pytest.mark.asyncio
async def test_offboard_user_tool_locks_and_reassigns(db_session):
    ws, ceo, successor, target = await _ceo(db_session)

    result = await call_tool(db_session, ceo, "offboard_user",
                             {"user_id": str(target.id), "successor_id": str(successor.id)})
    assert result["locked"] is True
    assert result["successor_id"] == str(successor.id)


@pytest.mark.asyncio
async def test_offboard_user_tool_wraps_forbidden_error(db_session):
    ws, ceo, successor, target = await _ceo(db_session)
    employee = User(workspace_id=ws.id, email="e@a.vn", password_hash="x", full_name="E",
                    role=Role.employee)
    db_session.add(employee)
    await db_session.commit()

    result = await call_tool(db_session, employee, "offboard_user", {"user_id": str(target.id)})
    assert result["error"] == "forbidden"
