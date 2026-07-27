import pytest

from app.agent.tools import SENSITIVE_TOOLS, TOOL_GROUPS, TOOLS, call_tool


async def test_suggest_replies_registered_not_sensitive():
    assert "suggest_replies" in TOOLS
    assert "suggest_replies" not in SENSITIVE_TOOLS
    assert "suggest_replies" in TOOL_GROUPS["core"]


async def test_call_tool_suggest_replies_returns_shown_true(db_session):
    result = await call_tool(db_session, None, "suggest_replies",
                             {"options": ["Co, tao task moi", "Khong"]})
    assert result == {"shown": True}


async def test_suggest_replies_input_requires_between_2_and_5_options():
    from pydantic import ValidationError

    from app.agent.tools import SuggestRepliesToolIn

    with pytest.raises(ValidationError):
        SuggestRepliesToolIn(options=["chi 1"])
    with pytest.raises(ValidationError):
        SuggestRepliesToolIn(options=[f"lua chon {i}" for i in range(6)])
    SuggestRepliesToolIn(options=["a", "b"])  # 2 phần tử — hợp lệ, không raise
