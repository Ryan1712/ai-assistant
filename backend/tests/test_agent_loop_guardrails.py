"""Guardrail hardening truoc Phase 3: chan agent loop dot chi phi ngoai MAX_ITERATIONS
(vd nhieu tool call/lan, chay qua lau tren gateway do tre cao, hoac ton qua nhieu token)."""
import pytest
from sqlalchemy import select

from app.agent.llm_client import FakeLLMClient, StreamDone, ToolUseBlock
from app.agent.loop import run_agent_loop
from app.agent.publisher import FakeEventPublisher
from app.models import (
    AgentTrace, ChatRequest, ChatRequestStatus, Conversation, Message, MessageRole, Role, User,
    Workspace,
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


def _tool_turn():
    return [StreamDone(tool_uses=[ToolUseBlock(id="t1", name="list_projects", input={})],
                       stop_reason="tool_use", input_tokens=1, output_tokens=1)]


@pytest.mark.asyncio
async def test_max_tool_calls_exceeded_stops_safely(db_session, monkeypatch):
    monkeypatch.setattr("app.agent.loop.MAX_TOOL_CALLS", 1)
    ws, ceo, conv = await _world(db_session)
    req = await _request(db_session, ws, conv, ceo)
    llm = FakeLLMClient(turns=[_tool_turn(), _tool_turn()])

    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    assert req.status == ChatRequestStatus.failed
    assert req.error == "max_tool_calls_exceeded"
    traces = (await db_session.execute(select(AgentTrace).where(
        AgentTrace.chat_request_id == req.id))).scalars().all()
    assert traces[-1].stop_reason == "max_tool_calls"


@pytest.mark.asyncio
async def test_max_duration_exceeded_stops_safely_before_any_llm_call(db_session, monkeypatch):
    monkeypatch.setattr("app.agent.loop.MAX_DURATION_SECONDS", -1)
    ws, ceo, conv = await _world(db_session)
    req = await _request(db_session, ws, conv, ceo)
    llm = FakeLLMClient(turns=[])

    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    assert req.status == ChatRequestStatus.failed
    assert req.error == "max_duration_exceeded"


@pytest.mark.asyncio
async def test_max_total_tokens_exceeded_stops_safely(db_session, monkeypatch):
    monkeypatch.setattr("app.agent.loop.MAX_TOTAL_TOKENS", 100)
    ws, ceo, conv = await _world(db_session)
    req = await _request(db_session, ws, conv, ceo)
    big_turn = [StreamDone(tool_uses=[ToolUseBlock(id="t1", name="list_projects", input={})],
                          stop_reason="tool_use", input_tokens=90, output_tokens=90)]
    llm = FakeLLMClient(turns=[big_turn])

    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    assert req.status == ChatRequestStatus.failed
    assert req.error == "max_total_tokens_exceeded"


@pytest.mark.asyncio
async def test_guardrails_do_not_trigger_for_normal_short_run(db_session):
    ws, ceo, conv = await _world(db_session)
    req = await _request(db_session, ws, conv, ceo)
    from app.agent.llm_client import TextDelta
    llm = FakeLLMClient(turns=[[
        TextDelta(text="Chao ban"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=10, output_tokens=3),
    ]])

    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    assert req.status == ChatRequestStatus.done
