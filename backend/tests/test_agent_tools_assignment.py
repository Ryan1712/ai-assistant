import pytest

from app.agent.tools import TOOLS, call_tool
from app.models import Role, User, Workspace


@pytest.mark.asyncio
async def test_suggest_assignee_tool_registered():
    assert "suggest_assignee" in TOOLS


@pytest.mark.asyncio
async def test_agent_tool_suggest_assignee_no_employees(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db_session.add(ceo)
    await db_session.commit()

    result = await call_tool(db_session, ceo, "suggest_assignee",
                             {"task_title": "Thiet ke landing page"})
    assert result["suggestions"] == []
