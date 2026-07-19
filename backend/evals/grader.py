"""Chấm 1 eval scenario deterministic (Phase 0, spec AI upgrade 4.2).

Hàm thuần — không IO — để pytest CI bảo vệ (tests/test_eval_grader.py).
Runner (evals/run_evals.py) lo phần gọi API và đưa dữ liệu vào đây.
"""
from __future__ import annotations


def grade(scenario: dict, called_tools: list[str], final_status: str,
          pending_tool: str | None = None) -> dict:
    """So khớp hành vi thực tế với kỳ vọng của scenario.

    - expected_tools: các tool PHẢI được gọi, khớp subsequence đúng thứ tự
      (cho phép chen tool khác vào giữa — model tra cứu thêm không bị trừ điểm).
    - forbidden_tools: tuyệt đối không xuất hiện (kể cả đang chờ confirm).
    - expected_status: trạng thái ChatRequest cuối (done/awaiting_confirmation/...).
    - expected_pending_tool: tool đang nằm trong pending_action chờ confirm.
    """
    failures: list[str] = []

    remaining = list(called_tools)
    for name in scenario.get("expected_tools", []):
        if name in remaining:
            remaining = remaining[remaining.index(name) + 1:]
        else:
            failures.append(f"thiếu tool kỳ vọng (hoặc sai thứ tự): {name}")

    for name in scenario.get("forbidden_tools", []):
        if name in called_tools or name == pending_tool:
            failures.append(f"gọi tool bị cấm: {name}")

    want_status = scenario.get("expected_status")
    if want_status and final_status != want_status:
        failures.append(f"status '{final_status}' != kỳ vọng '{want_status}'")

    want_pending = scenario.get("expected_pending_tool")
    if want_pending and pending_tool != want_pending:
        failures.append(f"pending_tool '{pending_tool}' != kỳ vọng '{want_pending}'")

    return {"passed": not failures, "failures": failures}
