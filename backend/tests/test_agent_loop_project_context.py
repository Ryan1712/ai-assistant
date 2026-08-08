"""PO #2 (2026-08-08): run_agent_loop tiêm đoạn hướng dẫn project mặc định
vào block động của system prompt khi conversation.project_id có giá trị —
cùng pattern rag_context/example_context (xem test_agent_loop_rag_context.py).
Xem docs/superpowers/plans/2026-08-08-conversation-project-scope.md."""
import pytest

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta
from app.agent.loop import run_agent_loop
from app.agent.publisher import FakeEventPublisher
from app.models import ChatRequest, Conversation, Project, Role, User, Workspace


async def _world(db, with_project: bool):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    project = None
    if with_project:
        project = Project(workspace_id=ws.id, name="Website Redesign", goal="",
                          created_by=ceo.id)
        db.add(project)
        await db.flush()
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id,
                        project_id=project.id if project else None)
    db.add(conv)
    await db.flush()
    return ws, ceo, conv


async def _request(db, ws, conv, ceo, content="tao task moi"):
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content=content, queue_position=1.0)
    db.add(req)
    await db.commit()
    return req


def _system_text(system) -> str:
    return system if isinstance(system, str) else "\n".join(b["text"] for b in system)


@pytest.mark.asyncio
async def test_run_agent_loop_injects_project_default_when_conv_has_project_id(db_session):
    ws, ceo, conv = await _world(db_session, with_project=True)
    req = await _request(db_session, ws, conv, ceo)
    llm = FakeLLMClient(turns=[[
        TextDelta(text="ok"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1),
    ]])

    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    text = _system_text(llm.calls[0]["system"])
    # LƯU Ý: snapshot_service (trạng thái công ty) CŨNG liệt kê tên mọi project
    # trong workspace như 1 nguồn ĐỘC LẬP với tính năng đang test ở đây — chỉ
    # assert tên project KHÔNG đủ phân biệt 2 nguồn. Phải assert đúng CÂU đặc
    # thù mà Task 4 sinh ra.
    assert "Project mặc định cho cuộc trò chuyện này" in text
    assert "Website Redesign" in text
    assert "create_task" in text


@pytest.mark.asyncio
async def test_run_agent_loop_no_project_hint_when_conv_has_no_project(db_session):
    ws, ceo, conv = await _world(db_session, with_project=False)
    req = await _request(db_session, ws, conv, ceo, content="hello")
    llm = FakeLLMClient(turns=[[
        TextDelta(text="ok"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1),
    ]])

    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    text = _system_text(llm.calls[0]["system"])
    assert "Project mặc định" not in text
