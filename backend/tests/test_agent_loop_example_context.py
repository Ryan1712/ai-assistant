"""Phase 6 §10.4: run_agent_loop nhận example_context (đã tính 1 lần lúc
worker pickup, xem app/agent/worker.py) và tiêm vào block động của system
prompt — cùng nguyên tắc rag_context (test_agent_loop_rag_context.py):
loop KHÔNG tự gọi build_example_block bên trong, chỉ nối chuỗi truyền sẵn."""
import pytest

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta
from app.agent.loop import run_agent_loop
from app.agent.publisher import FakeEventPublisher
from app.models import ChatRequest, Conversation, Message, MessageRole, Role, User, Workspace


async def _world(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id)
    db.add(conv)
    await db.flush()
    return ws, ceo, conv


async def _request(db, ws, conv, ceo, content="khoa acc Nam"):
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content=content, queue_position=1.0)
    db.add(req)
    db.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                   role=MessageRole.user, content=[{"type": "text", "text": content}]))
    await db.commit()
    return req


@pytest.mark.asyncio
async def test_example_context_appears_in_dynamic_system_block(db_session):
    ws, ceo, conv = await _world(db_session)
    req = await _request(db_session, ws, conv, ceo)
    llm = FakeLLMClient(turns=[[
        TextDelta(text="ok"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1),
    ]])

    await run_agent_loop(db_session, req, llm, FakeEventPublisher(),
                         example_context="# Ví dụ xử lý đúng\n- Tình huống: khoa acc\n  "
                         "Cách xử lý đúng: gọi lock_user ngay")

    system = llm.calls[0]["system"]
    assert isinstance(system, list) and len(system) == 2
    assert "Ví dụ xử lý đúng" not in system[0]["text"]  # tĩnh không chứa
    assert "gọi lock_user ngay" in system[1]["text"]


@pytest.mark.asyncio
async def test_no_example_context_means_no_extra_block(db_session):
    ws, ceo, conv = await _world(db_session)
    req = await _request(db_session, ws, conv, ceo)
    llm = FakeLLMClient(turns=[[
        TextDelta(text="ok"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1),
    ]])

    await run_agent_loop(db_session, req, llm, FakeEventPublisher(), example_context=None)

    system = llm.calls[0]["system"]
    if isinstance(system, list):
        assert "Ví dụ xử lý đúng" not in system[-1]["text"]
    else:
        assert "Ví dụ xử lý đúng" not in system
