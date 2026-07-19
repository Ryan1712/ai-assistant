"""Grader của eval harness (Phase 0, spec 4.2) — chấm deterministic."""
from evals.grader import grade


def test_subsequence_dung_thu_tu_pass():
    s = {"expected_tools": ["list_users", "assign_task"]}
    out = grade(s, ["list_projects", "list_users", "create_task", "assign_task"], "done")
    assert out["passed"] is True


def test_thieu_tool_ky_vong_fail():
    s = {"expected_tools": ["create_task"]}
    out = grade(s, ["list_tasks"], "done")
    assert out["passed"] is False
    assert "create_task" in out["failures"][0]


def test_sai_thu_tu_fail():
    s = {"expected_tools": ["create_task", "assign_task"]}
    out = grade(s, ["assign_task", "create_task"], "done")
    assert out["passed"] is False


def test_forbidden_o_called_hoac_pending_fail():
    s = {"forbidden_tools": ["lock_user"]}
    assert grade(s, ["lock_user"], "done")["passed"] is False
    assert grade(s, [], "awaiting_confirmation", pending_tool="lock_user")["passed"] is False
    assert grade(s, ["list_users"], "done")["passed"] is True


def test_expected_status_va_pending_tool():
    s = {"expected_status": "awaiting_confirmation", "expected_pending_tool": "send_email"}
    ok = grade(s, ["list_users"], "awaiting_confirmation", pending_tool="send_email")
    assert ok["passed"] is True
    bad = grade(s, ["list_users"], "done", pending_tool=None)
    assert bad["passed"] is False
    assert len(bad["failures"]) == 2


def test_scenario_rong_luon_pass():
    assert grade({}, ["anything"], "done")["passed"] is True
