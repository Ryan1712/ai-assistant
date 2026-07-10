import pytest

from app.agent.llm_client import FakeLLMClient, LLMClient, StreamDone, TextDelta
from app.agent.loop import run_agent_loop
from app.agent.publisher import FakeEventPublisher
from app.models import (
    ChatRequest, ChatRequestStatus, Conversation, Message, MessageRole, Role, User, Workspace,
)


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
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content="xin chao", queue_position=1.0)
    db.add(req)
    await db.flush()
    db.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                   role=MessageRole.user, content=[{"type": "text", "text": "xin chao"}]))
    await db.commit()
    return req


@pytest.mark.asyncio
async def test_cancelled_before_first_call_stops_immediately(db_session):
    req = await _world(db_session)
    llm = FakeLLMClient(turns=[])  # không được gọi
    pub = FakeEventPublisher()

    async def always_cancelled(_id):
        return True

    await run_agent_loop(db_session, req, llm, pub, is_cancelled=always_cancelled)

    assert req.status == ChatRequestStatus.cancelled
    assert len(llm.calls) == 0
    assert any(e["status"] == "cancelled" for _, e in pub.events)


@pytest.mark.asyncio
async def test_cancelled_mid_stream_keeps_partial_tokens_and_stops(db_session):
    req = await _world(db_session)
    llm = FakeLLMClient(turns=[[
        TextDelta(text="Dang "), TextDelta(text="lam"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1),
    ]])
    pub = FakeEventPublisher()
    calls = {"n": 0}

    async def cancel_on_third_check(_id):
        # 3 lần check trước khi hủy: (1) đầu while, (2) trước token "Dang ", (3) trước token "lam" -> True
        calls["n"] += 1
        return calls["n"] > 2

    await run_agent_loop(db_session, req, llm, pub, is_cancelled=cancel_on_third_check)

    assert req.status == ChatRequestStatus.cancelled
    tokens = [e for _, e in pub.events if e["type"] == "token"]
    assert len(tokens) == 1
    assert tokens[0]["text"] == "Dang "


@pytest.mark.asyncio
async def test_llm_error_marks_request_failed_without_raising(db_session):
    req = await _world(db_session)

    class _RaisingLLMClient(LLMClient):
        async def stream(self, *, system, messages, tools):
            raise RuntimeError("rate_limited_429")
            yield  # pragma: no cover - giữ hàm là generator

    pub = FakeEventPublisher()
    await run_agent_loop(db_session, req, _RaisingLLMClient(), pub)

    assert req.status == ChatRequestStatus.failed
    assert "rate_limited_429" in req.error
    assert any(e["type"] == "request_failed" for _, e in pub.events)
