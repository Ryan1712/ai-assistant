import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta
from app.agent.publisher import FakeEventPublisher
from app.agent.worker import process_conversation
from app.models import (
    ChatRequest, ChatRequestStatus, Conversation, Message, MessageRole, Role, User, Workspace,
)


async def test_process_conversation_nen_history_dai(engine, db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
               role=Role.ceo, is_root=True)
    db_session.add(ceo)
    await db_session.flush()
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id)
    db_session.add(conv)
    await db_session.flush()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(65):  # > SUMMARY_TRIGGER
        role = MessageRole.user if i % 2 == 0 else MessageRole.assistant
        db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, role=role,
                               content=[{"type": "text", "text": f"cu {i}"}],
                               created_at=base + timedelta(minutes=i)))
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content="xem dashboard hom nay", queue_position=100.0)  # heuristic -> khong deep
    db_session.add(req)
    await db_session.flush()
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                           role=MessageRole.user,
                           content=[{"type": "text", "text": "xem dashboard hom nay"}],
                           created_at=base + timedelta(minutes=100)))
    await db_session.commit()

    # Luot 1 = summary; luot 2 = tra loi agent loop cua req.
    llm = FakeLLMClient(turns=[
        [TextDelta(text="TOM TAT DA NEN"),
         StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)],
        [TextDelta(text="tra loi"),
         StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)],
    ])

    async def never_cancelled(_id):
        return False

    ctx = {
        "session_factory": async_sessionmaker(engine, expire_on_commit=False),
        "llm_client": llm,
        "event_publisher": FakeEventPublisher(),
        "is_cancelled": never_cancelled,
    }
    await process_conversation(ctx, conv.id)

    await db_session.refresh(conv)
    assert conv.rolling_summary == "TOM TAT DA NEN"
    assert conv.summary_through_at is not None
