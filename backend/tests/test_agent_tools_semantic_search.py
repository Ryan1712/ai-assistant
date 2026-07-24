import pytest

from app.agent.tools import TOOL_GROUPS, TOOLS, call_tool
from app.models import Role, User, Workspace
from app.services import note_service


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


def test_semantic_search_tool_registered_not_sensitive_and_in_core_group():
    assert "semantic_search" in TOOLS
    assert TOOLS["semantic_search"].sensitive is False
    assert "semantic_search" in TOOL_GROUPS["core"]
    assert len(TOOLS) == 59  # +create_directive +get_directive_status (Phase 3) +get_project_health +get_progress_stats (feedback fast-track) +semantic_search (Phase 6)


@pytest.mark.asyncio
async def test_semantic_search_tool_rejects_empty_query(db_session):
    ws, ceo = await _ceo(db_session)
    result = await call_tool(db_session, ceo, "semantic_search", {"query": ""})
    assert result["error"] == "invalid_input"


@pytest.mark.asyncio
async def test_semantic_search_tool_empty_result_has_explanatory_note(db_session):
    ws, ceo = await _ceo(db_session)
    result = await call_tool(db_session, ceo, "semantic_search", {"query": "khong lien quan gi"})
    assert result["results"] == []
    assert result.get("note")


@pytest.mark.asyncio
async def test_semantic_search_tool_finds_note_by_meaning(db_session):
    ws, ceo = await _ceo(db_session)
    await note_service.create_note(db_session, ceo, content="Nho ky hop dong voi doi tac ABC")

    result = await call_tool(db_session, ceo, "semantic_search",
                             {"query": "hop dong doi tac ABC", "source_types": ["note"]})
    assert len(result["results"]) == 1
    assert result["results"][0]["source_type"] == "note"
