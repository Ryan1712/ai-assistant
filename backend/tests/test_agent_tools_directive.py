import pytest
from sqlalchemy import select

from app.agent.tools import SENSITIVE_TOOLS, SNAPSHOT_WRITE_TOOLS, TOOL_GROUPS, TOOLS, call_tool
from app.models import User
from tests.conftest import _ceo_headers, _invite_and_join


def test_create_directive_registered_not_sensitive_snapshot_write():
    assert "create_directive" in TOOLS
    assert "create_directive" not in SENSITIVE_TOOLS
    assert "create_directive" in SNAPSHOT_WRITE_TOOLS
    assert "create_directive" in TOOL_GROUPS["work"]


def test_get_directive_status_registered_insight_group():
    assert "get_directive_status" in TOOLS
    assert "get_directive_status" not in SENSITIVE_TOOLS
    assert "get_directive_status" in TOOL_GROUPS["insight"]


def test_len_tools_bumped_for_directive():
    assert len(TOOLS) == 56  # +create_directive +get_directive_status (Phase 3)


@pytest.mark.asyncio
async def test_agent_tool_create_directive_end_to_end(client, db_session):
    ceo_h = await _ceo_headers(client)
    mgr = await _invite_and_join(client, ceo_h, "manager", "ha@a.vn")
    duy = await _invite_and_join(client, ceo_h, "employee", "duy@a.vn", mgr["user"]["id"])
    ceo = (await db_session.execute(select(User).where(User.email == "ceo@a.vn"))).scalar_one()

    result = await call_tool(db_session, ceo, "create_directive", {
        "recipient_id": duy["user"]["id"], "verbatim_text": "bao Duy xong deadline nhe",
    })

    assert result["status"] == "sent"
    assert result["recipient_id"] == duy["user"]["id"]


@pytest.mark.asyncio
async def test_agent_tool_get_directive_status_empty_has_note(client, db_session):
    ceo_h = await _ceo_headers(client)
    ceo = (await db_session.execute(select(User).where(User.email == "ceo@a.vn"))).scalar_one()

    result = await call_tool(db_session, ceo, "get_directive_status", {})

    assert result["directives"] == []
    assert result.get("note")
