"""PO #3 (2026-08-05 spec, 2026-08-08 plan): _resolve_proposal phải tự thay
placeholder $result[N].<field> bằng id thật của action N đã chạy, trước khi
gọi call_tool() cho action phụ thuộc — root cause bug thật: model gộp
add_employee+assign_task (hoặc create_project+create_task+assign_task) trong
1 propose_actions, action sau tham chiếu id của action trước bằng chuỗi
placeholder tự bịa, _resolve_proposal không hề thay id thật vào, Pydantic
validate UUID fail âm thầm -> outcome=partially_completed, CEO phải tự gán
lại bằng tay. Xem docs/superpowers/specs/2026-08-05-propose-actions-
placeholder-resolve-design.md."""
from app.agent.loop import _resolve_placeholder


def test_resolve_placeholder_thay_dung_field_tu_action_truoc():
    results = [
        {"tool_name": "add_employee", "display_text": "Thêm Duy Linh",
         "result": {"user_id": "11111111-1111-1111-1111-111111111111",
                    "full_name": "Duy Linh"}},
    ]
    tool_input = {"task_id": "22222222-2222-2222-2222-222222222222",
                 "user_id": "$result[0].user_id"}

    resolved, error = _resolve_placeholder(tool_input, 1, results)

    assert error is None
    assert resolved["user_id"] == "11111111-1111-1111-1111-111111111111"
    assert resolved["task_id"] == "22222222-2222-2222-2222-222222222222"


def test_resolve_placeholder_khong_co_placeholder_giu_nguyen():
    results = []
    tool_input = {"task_id": "22222222-2222-2222-2222-222222222222",
                 "user_id": "33333333-3333-3333-3333-333333333333"}

    resolved, error = _resolve_placeholder(tool_input, 0, results)

    assert error is None
    assert resolved == tool_input


def test_resolve_placeholder_action_nguon_fail_tra_loi():
    results = [
        {"tool_name": "add_employee", "display_text": "Thêm Duy Linh",
         "result": {"error": "invalid_input", "message": "email_taken"}},
    ]
    tool_input = {"task_id": "x", "user_id": "$result[0].user_id"}

    resolved, error = _resolve_placeholder(tool_input, 1, results)

    assert error is not None
    assert "Thêm Duy Linh" in error


def test_resolve_placeholder_field_khong_ton_tai_tra_loi():
    results = [
        {"tool_name": "add_employee", "display_text": "Thêm Duy Linh",
         "result": {"user_id": "11111111-1111-1111-1111-111111111111"}},
    ]
    tool_input = {"task_id": "x", "user_id": "$result[0].id"}  # sai ten field

    resolved, error = _resolve_placeholder(tool_input, 1, results)

    assert error is not None
    assert "id" in error


def test_resolve_placeholder_tu_tham_chieu_tra_loi():
    results = [{"tool_name": "a", "display_text": "A", "result": {"id": "x"}}]
    tool_input = {"user_id": "$result[0].id"}

    # action_index=0 tham chieu chinh no ($result[0]) -> N >= i
    resolved, error = _resolve_placeholder(tool_input, 0, results)

    assert error is not None


def test_resolve_placeholder_tham_chieu_tuong_lai_tra_loi():
    results = [{"tool_name": "a", "display_text": "A", "result": {"id": "x"}}]
    tool_input = {"user_id": "$result[5].id"}  # action 5 chua chay (N >= i)

    resolved, error = _resolve_placeholder(tool_input, 1, results)

    assert error is not None
