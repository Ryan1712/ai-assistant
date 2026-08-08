import pytest

from app.agent.llm_client import FakeLLMClient, StreamDone, ToolUseBlock
from app.agent.loop import resolve_confirmation, run_agent_loop
from app.agent.publisher import FakeEventPublisher
from app.models import (
    ChatRequest, ChatRequestStatus, Conversation, Message, MessageRole, Project, Role, Task,
    TaskAssignee, User, Workspace,
)


@pytest.mark.asyncio
async def test_ceo_giao_viec_cho_nguoi_moi_qua_propose_actions(db_session):
    """Mô phỏng đúng luồng CEO báo lỗi: giao việc cho người chưa có trong danh sách.
    AI (giả lập) phải đề xuất GỘP CẢ HAI add_employee + assign_task qua propose_actions
    trong 1 bản nháp — không hỏi lại, không tự chạy tool luôn (add_employee không
    sensitive nhưng đối tượng phải SUY LUẬN nên qua propose_actions theo luật 3 mức
    trong system prompt). Đây là crux của bug gốc: CEO không chỉ cần Duy Linh được
    THÊM vào danh bạ — CEO cần task ĐƯỢC GIAO cho Duy Linh.

    PO #3 (2026-08-08): dùng cú pháp $result[0].user_id (chuẩn mới) thay vì chuỗi
    placeholder tự bịa, và MỞ RỘNG test verify CẢ bước duyệt thật qua
    resolve_confirmation — đóng gap đã khiến bug gốc lọt qua (test cũ chỉ dừng ở
    bước tạo pending_action, không verify assign_task có thật sự chạy đúng)."""
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db_session.add(ceo)
    await db_session.flush()
    project = Project(workspace_id=ws.id, name="P", created_by=ceo.id)
    db_session.add(project)
    await db_session.flush()
    task = Task(workspace_id=ws.id, project_id=project.id, title="Thiet ke landing page",
               created_by=ceo.id)
    db_session.add(task)
    await db_session.flush()
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id)
    db_session.add(conv)
    await db_session.flush()
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content="giao viec thiet ke landing page cho Duy Linh",
                      queue_position=1.0)
    db_session.add(req)
    await db_session.flush()
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                           role=MessageRole.user, content=[{"type": "text", "text": req.content}]))
    await db_session.commit()

    actions = [
        {"tool_name": "add_employee", "tool_input": {"full_name": "Duy Linh"},
         "display_text": "Thêm Duy Linh vào danh sách nhân viên"},
        {"tool_name": "assign_task",
         "tool_input": {"task_id": str(task.id), "user_id": "$result[0].user_id"},
         "display_text": "Gán Duy Linh (vừa thêm ở trên) vào task Thiết kế landing page"},
    ]
    llm = FakeLLMClient(turns=[
        [StreamDone(tool_uses=[ToolUseBlock(
            id="t1", name="propose_actions",
            input={"actions": actions, "reasoning": "Duy Linh chưa có trong danh sách"})],
            stop_reason="tool_use", input_tokens=1, output_tokens=1)],
    ])

    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    await db_session.refresh(req)
    assert req.status == ChatRequestStatus.awaiting_confirmation
    assert req.pending_action["kind"] == "proposal"
    assert req.pending_action["actions"] == actions

    # PO #3: verify bước duyệt THẬT — Duy Linh phải được tạo VÀ gán vào task,
    # không chỉ dừng ở pending_action.
    await resolve_confirmation(db_session, req, True)
    await db_session.refresh(req)
    assert req.status == ChatRequestStatus.queued
    assert req.pending_action is None

    from sqlalchemy import select
    duy_linh = (await db_session.execute(
        select(User).where(User.workspace_id == ws.id, User.full_name == "Duy Linh")
    )).scalar_one()
    assignees = (await db_session.execute(
        select(TaskAssignee).where(TaskAssignee.task_id == task.id)
    )).scalars().all()
    assert len(assignees) == 1
    assert assignees[0].user_id == duy_linh.id
