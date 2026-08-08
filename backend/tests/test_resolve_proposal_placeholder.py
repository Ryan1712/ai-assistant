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


import pytest

from app.agent.loop import _resolve_proposal
from app.models import Project, Role, Task, User, Workspace


async def _world(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    project = Project(workspace_id=ws.id, name="P", created_by=ceo.id)
    db.add(project)
    await db.flush()
    task = Task(workspace_id=ws.id, project_id=project.id, title="Thiet ke landing page",
               created_by=ceo.id)
    db.add(task)
    await db.commit()
    return ws, ceo, task


@pytest.mark.asyncio
async def test_resolve_proposal_thay_placeholder_dung_id_that(db_session):
    ws, ceo, task = await _world(db_session)
    action = {
        "kind": "proposal",
        "actions": [
            {"tool_name": "add_employee", "tool_input": {"full_name": "Duy Linh"},
             "display_text": "Thêm Duy Linh vào danh sách nhân viên"},
            {"tool_name": "assign_task",
             "tool_input": {"task_id": str(task.id), "user_id": "$result[0].user_id"},
             "display_text": "Gán Duy Linh vào task Thiết kế landing page"},
        ],
        "reasoning": "Duy Linh chưa có trong danh sách",
    }
    trace_tools: list[dict] = []

    result = await _resolve_proposal(db_session, ceo, action, True, ws.id, trace_tools)

    assert result["outcome"] == "completed"
    assert result["failed"] == []
    assert len(result["succeeded"]) == 2
    assign_result = result["proposal_results"][1]["result"]
    assert "error" not in assign_result


@pytest.mark.asyncio
async def test_resolve_proposal_action_nguon_fail_skip_phu_thuoc_khong_side_effect(db_session):
    """Action nguồn (add_employee) fail vì thiếu full_name bắt buộc (Pydantic
    validate fail, xác nhận AddEmployeeToolIn.full_name: str không default trong
    tools.py) -> assign_task phụ thuộc PHẢI bị skip, KHÔNG gọi call_tool() thật
    (verify bằng cách task KHÔNG có assignee nào sau khi chạy)."""
    ws, ceo, task = await _world(db_session)
    action = {
        "kind": "proposal",
        "actions": [
            {"tool_name": "add_employee", "tool_input": {},  # thiếu full_name bắt buộc
             "display_text": "Thêm nhân viên (thiếu tên, cố ý gây lỗi)"},
            {"tool_name": "assign_task",
             "tool_input": {"task_id": str(task.id), "user_id": "$result[0].user_id"},
             "display_text": "Gán vào task"},
        ],
        "reasoning": "test",
    }
    trace_tools: list[dict] = []

    result = await _resolve_proposal(db_session, ceo, action, True, ws.id, trace_tools)

    assert result["outcome"] == "failed"
    assign_result = result["proposal_results"][1]["result"]
    assert assign_result["error"] == "dependency_failed"
    from sqlalchemy import select
    from app.models import TaskAssignee
    assignees = (await db_session.execute(
        select(TaskAssignee).where(TaskAssignee.task_id == task.id))).scalars().all()
    assert assignees == []


@pytest.mark.asyncio
async def test_resolve_proposal_khong_co_placeholder_van_chay_binh_thuong(db_session):
    """Backward compat: action không có placeholder chạy y hệt trước đây."""
    ws, ceo, task = await _world(db_session)
    action = {
        "kind": "proposal",
        "actions": [
            {"tool_name": "update_task",
             "tool_input": {"task_id": str(task.id), "percent": 50},
             "display_text": "Cập nhật task lên 50%"},
        ],
        "reasoning": "test",
    }
    trace_tools: list[dict] = []

    result = await _resolve_proposal(db_session, ceo, action, True, ws.id, trace_tools)

    assert result["outcome"] == "completed"
