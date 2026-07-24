"""Phase 6 §10.3 fast-follow: run_agent_loop nhận rag_context (đã tính 1 lần
lúc worker pickup, xem app/agent/worker.py) và tiêm vào block động của system
prompt — loop KHÔNG tự gọi embedding/semantic_search bên trong (khác snapshot/
instruction/rolling_summary vốn đọc DB mỗi vòng, rag_context chỉ là 1 string
truyền sẵn, dùng lại nguyên văn mọi vòng lặp của request)."""
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


async def _request(db, ws, conv, ceo, content="hoi lai chuyen cu"):
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content=content, queue_position=1.0)
    db.add(req)
    db.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                   role=MessageRole.user, content=[{"type": "text", "text": content}]))
    await db.commit()
    return req


@pytest.mark.asyncio
async def test_rag_context_appears_in_dynamic_system_block(db_session):
    ws, ceo, conv = await _world(db_session)
    req = await _request(db_session, ws, conv, ceo)
    llm = FakeLLMClient(turns=[[
        TextDelta(text="ok"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1),
    ]])

    await run_agent_loop(db_session, req, llm, FakeEventPublisher(),
                         rag_context="# Dữ liệu liên quan\n- [ghi chú] test XYZ")

    system = llm.calls[0]["system"]
    assert isinstance(system, list) and len(system) == 2
    assert "Dữ liệu liên quan" not in system[0]["text"]  # tĩnh không chứa
    assert "test XYZ" in system[1]["text"]


@pytest.mark.asyncio
async def test_no_rag_context_means_no_extra_block_when_nothing_else_dynamic(db_session):
    ws, ceo, conv = await _world(db_session)
    req = await _request(db_session, ws, conv, ceo)
    llm = FakeLLMClient(turns=[[
        TextDelta(text="ok"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1),
    ]])

    await run_agent_loop(db_session, req, llm, FakeEventPublisher(), rag_context=None)

    system = llm.calls[0]["system"]
    # snapshot rỗng (chưa có project/task) + không instruction + không rolling_summary
    # + không rag_context -> system vẫn có thể là str thuần (không block động nào).
    if isinstance(system, list):
        assert "Dữ liệu liên quan" not in system[-1]["text"]
    else:
        assert "Dữ liệu liên quan" not in system


@pytest.mark.asyncio
async def test_rag_context_reused_every_iteration_not_recomputed(db_session):
    """rag_context truyền sẵn phải giữ nguyên qua nhiều vòng lặp (không bị build lại
    /mất) — mô phỏng 1 vòng tool_use rồi 1 vòng trả lời."""
    from app.agent.llm_client import ToolUseBlock

    ws, ceo, conv = await _world(db_session)
    req = await _request(db_session, ws, conv, ceo, content="tao project Website")
    llm = FakeLLMClient(turns=[
        [StreamDone(tool_uses=[ToolUseBlock(id="t1", name="create_project",
                                            input={"name": "Website"})],
                    stop_reason="tool_use", input_tokens=1, output_tokens=1)],
        [TextDelta(text="xong"),
         StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)],
    ])

    await run_agent_loop(db_session, req, llm, FakeEventPublisher(),
                         rag_context="# Dữ liệu liên quan\n- [ghi chú] ABC")

    assert len(llm.calls) == 2
    for call in llm.calls:
        system = call["system"]
        text = system if isinstance(system, str) else "\n".join(b["text"] for b in system)
        assert "ABC" in text
