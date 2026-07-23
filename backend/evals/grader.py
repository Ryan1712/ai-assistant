"""Chấm 1 eval scenario deterministic (Phase 0, spec AI upgrade 4.2).

Hàm thuần — không IO — để pytest CI bảo vệ (tests/test_eval_grader.py).
Runner (evals/run_evals.py) lo phần gọi API và đưa dữ liệu vào đây.
"""
from __future__ import annotations


def grade(scenario: dict, called_tools: list[str], final_status: str,
          pending_tool: str | None = None, pending_kind: str | None = None,
          route: str | None = None) -> dict:
    """So khớp hành vi thực tế với kỳ vọng của scenario.

    - expected_tools: các tool PHẢI được gọi, khớp subsequence đúng thứ tự
      (cho phép chen tool khác vào giữa — model tra cứu thêm không bị trừ điểm).
    - expected_no_tools: fail nếu gọi bất kỳ tool nào (acceptance snapshot Phase 1).
    - forbidden_tools: tuyệt đối không xuất hiện (kể cả đang chờ confirm).
    - expected_status: trạng thái ChatRequest cuối (done/awaiting_confirmation/...).
    - expected_pending_tool: tool đang nằm trong pending_action chờ confirm.
    - expected_pending_kind: "tool" | "proposal" — propose_actions không bao giờ
      vào called_tools khi pause (chặn trước khi thực thi), nên scenario dùng
      propose_actions phải chấm bằng kind, không phải expected_tools/expected_pending_tool.
    - expected_route: route ("fast"/"deep"/"confirm") của dòng AgentTrace CUỐI
      CÙNG (Phase 4 §8 Router) — runner (run_evals.py) chịu trách nhiệm lấy đúng
      dòng cuối theo created_at, grader chỉ so khớp giá trị.
    """
    failures: list[str] = []

    remaining = list(called_tools)
    for name in scenario.get("expected_tools", []):
        if name in remaining:
            remaining = remaining[remaining.index(name) + 1:]
        else:
            failures.append(f"thiếu tool kỳ vọng (hoặc sai thứ tự): {name}")

    if scenario.get("expected_no_tools") and called_tools:
        failures.append("kỳ vọng 0 tool nhưng đã gọi: " + ", ".join(called_tools))

    for name in scenario.get("forbidden_tools", []):
        if name in called_tools or name == pending_tool:
            failures.append(f"gọi tool bị cấm: {name}")

    want_status = scenario.get("expected_status")
    if want_status and final_status != want_status:
        failures.append(f"status '{final_status}' != kỳ vọng '{want_status}'")

    want_pending = scenario.get("expected_pending_tool")
    if want_pending and pending_tool != want_pending:
        failures.append(f"pending_tool '{pending_tool}' != kỳ vọng '{want_pending}'")

    want_pending_kind = scenario.get("expected_pending_kind")
    if want_pending_kind and pending_kind != want_pending_kind:
        failures.append(f"pending_kind '{pending_kind}' != kỳ vọng '{want_pending_kind}'")

    want_route = scenario.get("expected_route")
    if want_route and route != want_route:
        failures.append(f"route '{route}' != kỳ vọng '{want_route}'")

    return {"passed": not failures, "failures": failures}
