import pytest

from app.agent.tools import TOOLS, call_tool
from tests.conftest import _ceo_headers


def test_resolver_tools_registered():
    assert "resolve_person" in TOOLS
    assert "resolve_task" in TOOLS
    assert len(TOOLS) == 58  # +create_directive +get_directive_status (Phase 3) +get_project_health +get_progress_stats (feedback fast-track)


@pytest.mark.asyncio
async def test_agent_tool_resolve_person(client, db_session):
    from sqlalchemy import select
    from app.models import User

    ceo_h = await _ceo_headers(client)
    ceo = (await db_session.execute(select(User).where(User.email == "ceo@a.vn"))).scalar_one()

    result = await call_tool(db_session, ceo, "resolve_person", {"query": "khong ai ten nay"})
    assert result["found"] is False


@pytest.mark.asyncio
async def test_agent_tool_resolve_task_requires_query_or_assignee(client, db_session):
    from sqlalchemy import select
    from app.models import User

    ceo_h = await _ceo_headers(client)
    ceo = (await db_session.execute(select(User).where(User.email == "ceo@a.vn"))).scalar_one()

    result = await call_tool(db_session, ceo, "resolve_task", {})
    assert result["error"] == "invalid_input"
