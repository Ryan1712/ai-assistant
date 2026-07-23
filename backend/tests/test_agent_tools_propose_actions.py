import pytest

from app.agent.tools import SENSITIVE_TOOLS, TOOLS, validate_proposal_actions


def test_propose_actions_registered_not_sensitive():
    assert "propose_actions" in TOOLS
    assert "propose_actions" not in SENSITIVE_TOOLS
    assert len(TOOLS) == 58  # +create_directive +get_directive_status (Phase 3) +get_project_health +get_progress_stats (feedback fast-track)


def test_validate_proposal_actions_empty_list_is_invalid():
    assert validate_proposal_actions([]) is not None


def test_validate_proposal_actions_unknown_tool_is_invalid():
    err = validate_proposal_actions([{"tool_name": "khong_ton_tai", "tool_input": {}}])
    assert err is not None
    assert "khong_ton_tai" in err


def test_validate_proposal_actions_sensitive_tool_is_invalid():
    err = validate_proposal_actions([{"tool_name": "lock_user", "tool_input": {}}])
    assert err is not None


def test_validate_proposal_actions_self_nesting_is_invalid():
    err = validate_proposal_actions([{"tool_name": "propose_actions", "tool_input": {}}])
    assert err is not None


def test_validate_proposal_actions_valid_returns_none():
    err = validate_proposal_actions([
        {"tool_name": "update_task", "tool_input": {"task_id": "x", "percent": 80}},
        {"tool_name": "create_note", "tool_input": {"content": "ghi chú"}},
    ])
    assert err is None
