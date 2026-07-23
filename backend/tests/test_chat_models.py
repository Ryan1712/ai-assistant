import pytest
from sqlalchemy import select

from app.models import (
    ChatRequest, ChatRequestStatus, Conversation, Message, MessageRole, Role,
    UsageLog, User, Workspace,
)


@pytest.mark.asyncio
async def test_conversation_chatrequest_message_usagelog_roundtrip(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    u = User(workspace_id=ws.id, email="c@a.vn", password_hash="x",
             full_name="C", role=Role.ceo, is_root=True)
    db_session.add(u)
    await db_session.flush()

    conv = Conversation(workspace_id=ws.id, user_id=u.id)
    db_session.add(conv)
    await db_session.flush()

    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=u.id,
                      content="tao task X", queue_position=1.0)
    db_session.add(req)
    await db_session.flush()

    msg = Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                  role=MessageRole.user, content=[{"type": "text", "text": "tao task X"}])
    db_session.add(msg)
    db_session.add(UsageLog(workspace_id=ws.id, chat_request_id=req.id,
                            model="claude-haiku-4-5", input_tokens=10, output_tokens=5))
    await db_session.commit()

    found_req = (await db_session.execute(select(ChatRequest))).scalar_one()
    assert found_req.status == ChatRequestStatus.queued
    assert found_req.queue_position == 1.0
    assert found_req.pending_action is None

    found_msg = (await db_session.execute(select(Message))).scalar_one()
    assert found_msg.role == MessageRole.user
    assert found_msg.content == [{"type": "text", "text": "tao task X"}]

    found_usage = (await db_session.execute(select(UsageLog))).scalar_one()
    assert found_usage.model == "claude-haiku-4-5"


@pytest.mark.asyncio
async def test_chat_request_status_has_deep_running(db_session):
    """Phase 4 (Router + đường sâu async): trạng thái "đã ack, đang chạy nền" —
    ChatRequest ở trạng thái này KHÔNG phải done/failed/cancelled."""
    assert ChatRequestStatus.deep_running.value == "deep_running"

    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    u = User(workspace_id=ws.id, email="d@a.vn", password_hash="x",
             full_name="D", role=Role.ceo, is_root=True)
    db_session.add(u)
    await db_session.flush()
    conv = Conversation(workspace_id=ws.id, user_id=u.id)
    db_session.add(conv)
    await db_session.flush()

    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=u.id,
                      content="danh gia rui ro toan bo du an", queue_position=1.0,
                      status=ChatRequestStatus.deep_running)
    db_session.add(req)
    await db_session.commit()

    found = (await db_session.execute(select(ChatRequest).where(
        ChatRequest.id == req.id))).scalar_one()
    assert found.status == ChatRequestStatus.deep_running
