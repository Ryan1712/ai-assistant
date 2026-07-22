"""Hardening truoc Phase 3: UsageLog ghi them user_id/feature/status/latency_ms/
tool_call_count/iteration/estimated_cost de tra loi duoc "feature/user nao ton tien"
ma khong can bang/service moi (spec: mo rong UsageLog vua du)."""
import pytest
from sqlalchemy import select

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta, ToolUseBlock
from app.agent.loop import run_agent_loop
from app.agent.publisher import FakeEventPublisher
from app.models import (
    ChatRequest, Conversation, Message, MessageRole, Role, UsageLog, User, Workspace,
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
    await db.commit()
    return ws, ceo, conv


async def _request(db, ws, conv, ceo, content="xin chao"):
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content=content, queue_position=1.0)
    db.add(req)
    db.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                   role=MessageRole.user, content=[{"type": "text", "text": content}]))
    await db.commit()
    return req


@pytest.mark.asyncio
async def test_usage_log_records_user_feature_status_latency_and_iteration(db_session):
    ws, ceo, conv = await _world(db_session)
    req = await _request(db_session, ws, conv, ceo)
    llm = FakeLLMClient(turns=[[
        TextDelta(text="Chao ban"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=10, output_tokens=3),
    ]], model="claude-haiku-4-5-20251001")

    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    (usage,) = (await db_session.execute(select(UsageLog))).scalars().all()
    assert usage.user_id == ceo.id
    assert usage.feature == "chat"
    assert usage.status == "end_turn"
    assert usage.latency_ms >= 0
    assert usage.tool_call_count == 0
    assert usage.iteration == 1


@pytest.mark.asyncio
async def test_usage_log_tool_call_count_matches_tool_uses_in_that_turn(db_session):
    ws, ceo, conv = await _world(db_session)
    req = await _request(db_session, ws, conv, ceo)
    llm = FakeLLMClient(turns=[
        [StreamDone(tool_uses=[
            ToolUseBlock(id="t1", name="list_projects", input={}),
            ToolUseBlock(id="t2", name="list_tasks", input={}),
         ], stop_reason="tool_use", input_tokens=20, output_tokens=10)],
        [TextDelta(text="Xong"),
         StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=5, output_tokens=2)],
    ], model="claude-haiku-4-5-20251001")

    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    rows = (await db_session.execute(select(UsageLog).order_by(UsageLog.created_at))).scalars().all()
    assert len(rows) == 2
    assert rows[0].tool_call_count == 2
    assert rows[0].status == "tool_use"
    assert rows[0].iteration == 1
    assert rows[1].tool_call_count == 0
    assert rows[1].iteration == 2


@pytest.mark.asyncio
async def test_usage_log_estimated_cost_zero_for_unknown_dev_gateway_model(db_session):
    ws, ceo, conv = await _world(db_session)
    req = await _request(db_session, ws, conv, ceo)
    llm = FakeLLMClient(turns=[[
        TextDelta(text="Chao ban"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=10, output_tokens=3),
    ]], model="glm-4.7-flash")

    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    (usage,) = (await db_session.execute(select(UsageLog))).scalars().all()
    assert usage.estimated_cost == 0.0


@pytest.mark.asyncio
async def test_usage_log_estimated_cost_positive_for_known_anthropic_model(db_session):
    ws, ceo, conv = await _world(db_session)
    req = await _request(db_session, ws, conv, ceo)
    llm = FakeLLMClient(turns=[[
        TextDelta(text="Chao ban"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1_000_000, output_tokens=1_000_000),
    ]], model="anthropic/claude-haiku-4-5-20251001")

    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    (usage,) = (await db_session.execute(select(UsageLog))).scalars().all()
    assert usage.estimated_cost > 0.0
