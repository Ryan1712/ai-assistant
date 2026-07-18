import uuid

import pytest
from pydantic import BaseModel

from app.agent import tools as tools_mod
from app.agent.tools import ToolSpec, call_tool
from app.models import Role, User


@pytest.fixture
def actor():
    return User(id=uuid.uuid4(), workspace_id=uuid.uuid4(), email="a@b.c",
                password_hash="x", full_name="A", role=Role.ceo)


class _NoArgs(BaseModel):
    pass


async def test_loi_bat_ngo_trong_handler_thanh_tool_result(actor, monkeypatch):
    async def boom(db, actor, body):
        raise ValueError("something exploded")
    monkeypatch.setitem(tools_mod.TOOLS, "boom_tool",
                        ToolSpec(name="boom_tool", description="", input_model=_NoArgs,
                                 handler=boom))
    result = await call_tool(None, actor, "boom_tool", {})
    assert result["error"] == "tool_failed"
    assert "something exploded" in result["message"]
