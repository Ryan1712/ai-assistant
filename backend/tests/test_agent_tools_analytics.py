import pytest
from sqlalchemy import select

from app.agent.tools import SENSITIVE_TOOLS, SNAPSHOT_WRITE_TOOLS, TOOL_GROUPS, TOOLS, call_tool
from app.models import Project, User
from tests.conftest import _ceo_headers


def test_get_project_health_registered_insight_readonly():
    assert "get_project_health" in TOOLS
    assert "get_project_health" not in SENSITIVE_TOOLS
    assert "get_project_health" not in SNAPSHOT_WRITE_TOOLS
    assert "get_project_health" in TOOL_GROUPS["insight"]


def test_get_progress_stats_registered_insight_readonly():
    assert "get_progress_stats" in TOOLS
    assert "get_progress_stats" not in SENSITIVE_TOOLS
    assert "get_progress_stats" not in SNAPSHOT_WRITE_TOOLS
    assert "get_progress_stats" in TOOL_GROUPS["insight"]


def test_len_tools_bumped_for_analytics():
    assert len(TOOLS) == 58  # +get_project_health +get_progress_stats (feedback fast-track)


@pytest.mark.asyncio
async def test_agent_tool_get_project_health_empty_project_has_note(client, db_session):
    ceo_h = await _ceo_headers(client)
    ceo = (await db_session.execute(select(User).where(User.email == "ceo@a.vn"))).scalar_one()
    project = Project(workspace_id=ceo.workspace_id, name="Du an rong", created_by=ceo.id)
    db_session.add(project)
    await db_session.commit()

    result = await call_tool(db_session, ceo, "get_project_health", {"project_id": str(project.id)})

    assert result["task_total"] == 0
    assert result["risk"] == "low"
    assert result.get("note")


@pytest.mark.asyncio
async def test_agent_tool_get_project_health_not_found(client, db_session):
    ceo_h = await _ceo_headers(client)
    ceo = (await db_session.execute(select(User).where(User.email == "ceo@a.vn"))).scalar_one()

    result = await call_tool(db_session, ceo, "get_project_health",
                             {"project_id": "00000000-0000-0000-0000-000000000000"})

    assert result["error"] == "not_found"


@pytest.mark.asyncio
async def test_agent_tool_get_progress_stats_empty_scope_has_note(client, db_session):
    ceo_h = await _ceo_headers(client)
    ceo = (await db_session.execute(select(User).where(User.email == "ceo@a.vn"))).scalar_one()

    result = await call_tool(db_session, ceo, "get_progress_stats", {})

    assert result["period"] == "week"
    assert result["current"] == {"completed": 0, "created": 0, "overdue": 0}
    assert result.get("note")


@pytest.mark.asyncio
async def test_agent_tool_get_progress_stats_invalid_period(client, db_session):
    ceo_h = await _ceo_headers(client)
    ceo = (await db_session.execute(select(User).where(User.email == "ceo@a.vn"))).scalar_one()

    result = await call_tool(db_session, ceo, "get_progress_stats", {"period": "quarter"})

    assert result["error"] == "invalid_input"
