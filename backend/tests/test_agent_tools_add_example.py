import pytest

from app.agent.tools import TOOL_GROUPS, TOOLS, call_tool
from app.models import Role, User, Workspace


async def _users(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    employee = User(workspace_id=ws.id, email="e@a.vn", password_hash="x", full_name="E",
                    role=Role.employee)
    db.add_all([ceo, employee])
    await db.flush()
    await db.commit()
    return ws, ceo, employee


def test_add_example_tool_registered_not_sensitive_and_in_skill_instruction_group():
    assert "add_example" in TOOLS
    assert TOOLS["add_example"].sensitive is False
    assert "add_example" in TOOL_GROUPS["skill_instruction"]


@pytest.mark.asyncio
async def test_add_example_tool_creates_workspace_scoped_example(db_session):
    ws, ceo, employee = await _users(db_session)

    result = await call_tool(db_session, ceo, "add_example",
                             {"user_text": "khoa acc thang Nam",
                              "ideal_behavior": "gọi lock_user ngay, không hỏi lại"})

    assert result["workspace_id"] == str(ws.id)
    assert "id" in result


@pytest.mark.asyncio
async def test_add_example_tool_requires_ceo(db_session):
    ws, ceo, employee = await _users(db_session)

    result = await call_tool(db_session, employee, "add_example",
                             {"user_text": "x", "ideal_behavior": "y"})

    assert result["error"] == "forbidden"
