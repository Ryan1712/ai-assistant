import pytest

from app.agent.tools import call_tool
from app.models import Role, User, Workspace


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


@pytest.mark.asyncio
async def test_create_note_and_list_own_only(db_session):
    ws, ceo, emp = await _world(db_session)
    created = await call_tool(db_session, emp, "create_note",
                              {"content": "ghi chu rieng", "tags": ["y-tuong"]})
    assert created["content"] == "ghi chu rieng"

    mine = await call_tool(db_session, emp, "list_notes", {})
    assert len(mine["notes"]) == 1

    ceo_view = await call_tool(db_session, ceo, "list_notes", {})
    assert ceo_view["notes"] == []


@pytest.mark.asyncio
async def test_list_notes_filter_by_tag(db_session):
    ws, ceo, emp = await _world(db_session)
    await call_tool(db_session, ceo, "create_note", {"content": "a", "tags": ["x"]})
    await call_tool(db_session, ceo, "create_note", {"content": "b", "tags": ["y"]})
    got = await call_tool(db_session, ceo, "list_notes", {"tag": "y"})
    assert [n["content"] for n in got["notes"]] == ["b"]
