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
    await db.commit()
    return ws, ceo


def test_search_tool_registered_and_not_sensitive():
    assert "search" in TOOLS
    assert TOOLS["search"].sensitive is False
    assert len(TOOLS) == 47  # +get/set_notification_preference (2026-07-17)


@pytest.mark.asyncio
async def test_search_tool_returns_all_groups_empty_when_no_match(db_session):
    ws, ceo = await _ceo(db_session)

    result = await call_tool(db_session, ceo, "search", {"q": "khong ton tai"})
    assert result == {"tasks": [], "notes": [], "voice_notes": [], "users": [], "skills": []}


@pytest.mark.asyncio
async def test_search_tool_rejects_empty_query(db_session):
    ws, ceo = await _ceo(db_session)

    result = await call_tool(db_session, ceo, "search", {"q": ""})
    assert result["error"] == "invalid_input"
