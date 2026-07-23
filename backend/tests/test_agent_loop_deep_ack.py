"""Phase 4 (đường sâu, §8.2): run_deep_ack_turn - lượt đầu model_fast KHÔNG
tool, chỉ tạo ack ngắn rồi chuyển request sang deep_running (job phân tích nền
enqueue ở tầng gọi, worker.py - task 7/8, chưa test ở đây)."""
import pytest
from sqlalchemy import select

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta
from app.agent.loop import run_deep_ack_turn
from app.agent.publisher import FakeEventPublisher
from app.models import (
    AgentTrace, ChatRequest, ChatRequestStatus, Conversation, Message, MessageRole, Role, User,
    Workspace,
)


async def _world(db, content="danh gia rui ro toan bo du an thang nay"):
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
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content=content, queue_position=1.0)
    db.add(req)
    db.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                   role=MessageRole.user, content=[{"type": "text", "text": content}]))
    await db.commit()
    return ws, ceo, conv, req


@pytest.mark.asyncio
async def test_ack_turn_writes_message_and_deep_running_status(db_session):
    ws, ceo, conv, req = await _world(db_session)
    llm = FakeLLMClient(turns=[[
        TextDelta(text="Đang phân tích rủi ro dự án, khoảng 30 giây nhé."),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=5, output_tokens=10),
    ]], model="claude-haiku-4-5")
    publisher = FakeEventPublisher()

    await run_deep_ack_turn(db_session, req, llm, publisher)

    assert req.status == ChatRequestStatus.deep_running
    (msg,) = (await db_session.execute(select(Message).where(
        Message.role == MessageRole.assistant))).scalars().all()
    assert msg.content == [{"type": "text",
                           "text": "Đang phân tích rủi ro dự án, khoảng 30 giây nhé."}]
    # tools=[] luôn - ack không được phép gọi tool
    assert llm.calls[0]["tools"] == []


@pytest.mark.asyncio
async def test_ack_turn_publishes_deep_analysis_started_not_request_done(db_session):
    ws, ceo, conv, req = await _world(db_session)
    llm = FakeLLMClient(turns=[[
        TextDelta(text="ok"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1),
    ]])
    publisher = FakeEventPublisher()

    await run_deep_ack_turn(db_session, req, llm, publisher)

    event_types = [event["type"] for _conv_id, event in publisher.events]
    assert "deep_analysis_started" in event_types
    assert "request_done" not in event_types


@pytest.mark.asyncio
async def test_ack_turn_writes_agent_trace_route_deep(db_session):
    ws, ceo, conv, req = await _world(db_session)
    llm = FakeLLMClient(turns=[[
        TextDelta(text="ok"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1),
    ]])

    await run_deep_ack_turn(db_session, req, llm, FakeEventPublisher())

    (trace,) = (await db_session.execute(select(AgentTrace).where(
        AgentTrace.chat_request_id == req.id))).scalars().all()
    assert trace.route == "deep"
    assert trace.stop_reason == "ack_sent"


@pytest.mark.asyncio
async def test_ack_turn_empty_reply_falls_back_to_default_text(db_session):
    ws, ceo, conv, req = await _world(db_session)
    llm = FakeLLMClient(turns=[[
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=0),
    ]])

    await run_deep_ack_turn(db_session, req, llm, FakeEventPublisher())

    (msg,) = (await db_session.execute(select(Message).where(
        Message.role == MessageRole.assistant))).scalars().all()
    assert msg.content[0]["text"]  # không rỗng


@pytest.mark.asyncio
async def test_ack_turn_llm_error_marks_request_failed(db_session):
    ws, ceo, conv, req = await _world(db_session)
    llm = FakeLLMClient(turns=[])  # .stream() gọi -> pop(0) rỗng -> IndexError

    await run_deep_ack_turn(db_session, req, llm, FakeEventPublisher())

    assert req.status == ChatRequestStatus.failed


@pytest.mark.asyncio
async def test_ack_turn_cancelled_before_start_marks_cancelled(db_session):
    ws, ceo, conv, req = await _world(db_session)
    llm = FakeLLMClient(turns=[])  # không được gọi

    async def always_cancelled(_id):
        return True

    await run_deep_ack_turn(db_session, req, llm, FakeEventPublisher(),
                            is_cancelled=always_cancelled)

    assert req.status == ChatRequestStatus.cancelled
    assert len(llm.calls) == 0
