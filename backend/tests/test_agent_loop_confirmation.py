import json

import pytest
from sqlalchemy import select

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta
from app.agent.loop import resolve_confirmation, run_agent_loop
from app.agent.publisher import FakeEventPublisher
from app.models import (
    AgentTrace, ChatRequest, ChatRequestStatus, Conversation, Message, Role, User, UserStatus,
    Workspace,
)


async def _world(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    target = User(workspace_id=ws.id, email="e@a.vn", password_hash="x", full_name="E",
                  role=Role.employee)
    db.add_all([ceo, target])
    await db.flush()
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id)
    db.add(conv)
    await db.flush()
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content="khoa e@a.vn", queue_position=1.0,
                      status=ChatRequestStatus.awaiting_confirmation,
                      pending_action={"tool_name": "lock_user",
                                     "tool_input": {"target_id": str(target.id)},
                                     "tool_use_id": "t1"})
    db.add(req)
    await db.flush()
    await db.commit()
    return ws, ceo, target, conv, req


@pytest.mark.asyncio
async def test_resolve_confirmation_approved_executes_tool_and_requeues(db_session):
    ws, ceo, target, conv, req = await _world(db_session)

    await resolve_confirmation(db_session, req, approved=True)

    await db_session.refresh(target)
    assert target.status == UserStatus.locked
    assert req.status == ChatRequestStatus.queued
    assert req.pending_action is None

    msgs = (await db_session.execute(select(Message))).scalars().all()
    tool_result = [m for m in msgs if m.content[0]["type"] == "tool_result"][0]
    assert json.loads(tool_result.content[0]["content"])["locked"] is True


@pytest.mark.asyncio
async def test_resolve_confirmation_approved_writes_agent_trace(db_session):
    ws, ceo, target, conv, req = await _world(db_session)

    await resolve_confirmation(db_session, req, approved=True)

    traces = (await db_session.execute(select(AgentTrace))).scalars().all()
    assert len(traces) == 1
    trace = traces[0]
    assert trace.chat_request_id == req.id
    assert trace.workspace_id == ws.id
    assert trace.route == "confirm"
    assert len(trace.tools_called) == 1
    assert trace.tools_called[0]["name"] == "lock_user"


@pytest.mark.asyncio
async def test_resolve_confirmation_denied_writes_no_agent_trace(db_session):
    ws, ceo, target, conv, req = await _world(db_session)

    await resolve_confirmation(db_session, req, approved=False)

    traces = (await db_session.execute(select(AgentTrace))).scalars().all()
    assert traces == []


@pytest.mark.asyncio
async def test_resolve_confirmation_denied_does_not_execute_tool(db_session):
    ws, ceo, target, conv, req = await _world(db_session)

    await resolve_confirmation(db_session, req, approved=False)

    await db_session.refresh(target)
    assert target.status == UserStatus.active
    assert req.status == ChatRequestStatus.queued
    msgs = (await db_session.execute(select(Message))).scalars().all()
    tool_result = [m for m in msgs if m.content[0]["type"] == "tool_result"][0]
    assert json.loads(tool_result.content[0]["content"])["error"] == "user_denied"


@pytest.mark.asyncio
async def test_run_agent_loop_completes_after_confirmation_resolved(db_session):
    ws, ceo, target, conv, req = await _world(db_session)
    await resolve_confirmation(db_session, req, approved=True)

    llm = FakeLLMClient(turns=[[
        TextDelta(text="Da khoa tai khoan."),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=8, output_tokens=4),
    ]])
    pub = FakeEventPublisher()
    await run_agent_loop(db_session, req, llm, pub)

    assert req.status == ChatRequestStatus.done
    sent_messages = llm.calls[0]["messages"]
    assert any(
        isinstance(block, dict) and block.get("type") == "tool_result"
        for msg in sent_messages for block in msg["content"]
    )
