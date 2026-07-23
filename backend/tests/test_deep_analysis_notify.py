"""Phase 4 §8.2 Task 9: job run_deep_analysis xong (status -> done) phải báo cho
người gửi qua notify() (in-app Notification + push best-effort) - CEO/manager
không ngồi chờ 30s-800s, cần được nhắc khi kết quả đã sẵn sàng."""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta
from app.agent.publisher import FakeEventPublisher
from app.agent.worker import run_deep_analysis
from app.models import (
    ChatRequest, ChatRequestStatus, Conversation, Device, Message, MessageRole, Notification,
    Role, User, Workspace,
)
from app.services import push_service


@pytest.fixture(autouse=True)
def _reset_mock_push():
    push_service.mock_push_client.sent.clear()
    yield
    push_service.mock_push_client.sent.clear()


async def _world_deep_running(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    db.add(Device(workspace_id=ws.id, user_id=ceo.id, device_uuid="d-1",
                  push_token="ExponentPushToken[ceo]"))
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id)
    db.add(conv)
    await db.flush()
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content="phan tich rui ro du an", queue_position=1.0,
                      status=ChatRequestStatus.deep_running)
    db.add(req)
    await db.flush()
    db.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                   role=MessageRole.user, content=[{"type": "text", "text": req.content}]))
    await db.commit()
    return ws, ceo, conv, req


@pytest.mark.asyncio
async def test_run_deep_analysis_notifies_sender_when_done(engine, db_session):
    ws, ceo, conv, req = await _world_deep_running(db_session)
    llm_smart = FakeLLMClient(turns=[
        [TextDelta(text="ket qua phan tich sau"),
         StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)],
    ])

    async def never_cancelled(_id):
        return False

    ctx = {
        "session_factory": async_sessionmaker(engine, expire_on_commit=False),
        "llm_client_smart": llm_smart,
        "event_publisher": FakeEventPublisher(),
        "is_cancelled": never_cancelled,
    }

    await run_deep_analysis(ctx, req.id)

    await db_session.refresh(req)
    assert req.status == ChatRequestStatus.done
    (notif,) = (await db_session.execute(select(Notification).where(
        Notification.recipient_id == ceo.id))).scalars().all()
    assert notif.type == "deep_analysis_done"
    assert notif.payload["chat_request_id"] == str(req.id)
    assert notif.payload["conversation_id"] == str(req.conversation_id)

    sent = push_service.mock_push_client.sent
    assert len(sent) == 1
    tokens, title, body, data = sent[0]
    assert tokens == ["ExponentPushToken[ceo]"]
    assert data["type"] == "deep_analysis_done"


@pytest.mark.asyncio
async def test_run_deep_analysis_does_not_notify_when_cancelled(engine, db_session):
    """Job bị hủy giữa chừng (CEO bấm dừng) - không phải kết quả thật, không báo
    "đã xong" gây hiểu lầm."""
    ws, ceo, conv, req = await _world_deep_running(db_session)
    llm_smart = FakeLLMClient(turns=[])

    async def always_cancelled(_id):
        return True

    ctx = {
        "session_factory": async_sessionmaker(engine, expire_on_commit=False),
        "llm_client_smart": llm_smart,
        "event_publisher": FakeEventPublisher(),
        "is_cancelled": always_cancelled,
    }

    await run_deep_analysis(ctx, req.id)

    await db_session.refresh(req)
    assert req.status == ChatRequestStatus.cancelled
    notifs = (await db_session.execute(select(Notification).where(
        Notification.recipient_id == ceo.id))).scalars().all()
    assert notifs == []
    assert push_service.mock_push_client.sent == []
