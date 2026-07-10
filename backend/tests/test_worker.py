import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta
from app.agent.publisher import FakeEventPublisher
from app.agent.worker import WorkerSettings, enqueue_conversation, process_conversation
from app.models import (
    ChatRequest, ChatRequestStatus, Conversation, Message, MessageRole, Role, User, Workspace,
)


@pytest.mark.asyncio
async def test_process_conversation_runs_queued_requests_in_order_then_stops(engine, db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db_session.add(ceo)
    await db_session.flush()
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id)
    other_conv = Conversation(workspace_id=ws.id, user_id=ceo.id)
    db_session.add_all([conv, other_conv])
    await db_session.flush()

    req1 = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                       content="mot", queue_position=1.0)
    req2 = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                       content="hai", queue_position=2.0)
    other_req = ChatRequest(workspace_id=ws.id, conversation_id=other_conv.id, user_id=ceo.id,
                            content="khac conversation", queue_position=1.0)
    db_session.add_all([req1, req2, other_req])
    await db_session.flush()
    for req in (req1, req2, other_req):
        db_session.add(Message(workspace_id=ws.id, conversation_id=req.conversation_id,
                               chat_request_id=req.id, role=MessageRole.user,
                               content=[{"type": "text", "text": req.content}]))
    await db_session.commit()

    llm = FakeLLMClient(turns=[
        [TextDelta(text="tra loi 1"),
         StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)],
        [TextDelta(text="tra loi 2"),
         StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)],
    ])
    pub = FakeEventPublisher()

    async def never_cancelled(_id):
        return False

    ctx = {
        "session_factory": async_sessionmaker(engine, expire_on_commit=False),
        "llm_client": llm,
        "event_publisher": pub,
        "is_cancelled": never_cancelled,
    }

    await process_conversation(ctx, conv.id)

    await db_session.refresh(req1)
    await db_session.refresh(req2)
    await db_session.refresh(other_req)
    assert req1.status == ChatRequestStatus.done
    assert req2.status == ChatRequestStatus.done
    assert other_req.status == ChatRequestStatus.queued  # conversation khác không bị đụng tới
    assert len(llm.calls) == 2


@pytest.mark.asyncio
async def test_enqueue_conversation_uses_conversation_scoped_job_id():
    class _FakePool:
        def __init__(self):
            self.calls = []

        async def enqueue_job(self, name, *args, **kwargs):
            self.calls.append((name, args, kwargs))
            return "job-handle"

    pool = _FakePool()
    conv_id = uuid.uuid4()
    result = await enqueue_conversation(pool, conv_id)

    assert result == "job-handle"
    name, args, kwargs = pool.calls[0]
    assert name == "process_conversation"
    assert args == (conv_id,)
    assert kwargs["_job_id"] == f"conv:{conv_id}"


def test_worker_settings_registers_process_conversation():
    assert process_conversation in WorkerSettings.functions
    assert WorkerSettings.redis_settings is not None


def test_worker_settings_has_explicit_max_jobs_and_job_timeout():
    """Finding 3 (final review): max_jobs bounds how many conversations can run
    Claude calls concurrently (per design spec); job_timeout must comfortably exceed
    MAX_ITERATIONS' realistic wall-clock time so the loop's own cap (Finding 2) is
    what normally ends a runaway job, not arq killing it via CancelledError."""
    assert WorkerSettings.max_jobs == 10
    assert WorkerSettings.job_timeout == 600
