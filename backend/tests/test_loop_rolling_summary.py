import uuid
from datetime import datetime, timedelta, timezone

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta
from app.agent.loop import run_agent_loop
from app.agent.publisher import FakeEventPublisher
from app.models import (
    ChatRequest, ChatRequestStatus, Conversation, Message, MessageRole, Role, User, Workspace,
)


async def _seed(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
               role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    return ws, ceo


async def test_rolling_summary_vao_system_khong_vao_messages(db_session):
    ws, ceo = await _seed(db_session)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id,
                        rolling_summary="TOM TAT CU: da giao Duy task X",
                        summary_through_at=base)
    db_session.add(conv)
    await db_session.flush()
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content="tiep theo lam gi", queue_position=1.0)
    db_session.add(req)
    await db_session.flush()
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                           role=MessageRole.user,
                           content=[{"type": "text", "text": "tiep theo lam gi"}],
                           created_at=base + timedelta(minutes=1)))  # SAU moc
    await db_session.commit()

    llm = FakeLLMClient(turns=[[TextDelta(text="ok"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)]])
    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    call = llm.calls[0]
    system = call["system"]
    system_text = system if isinstance(system, str) else "\n".join(
        b["text"] for b in system if b.get("type") == "text")
    assert "TOM TAT CU: da giao Duy task X" in system_text
    # summary KHONG duoc la 1 message trong lich su
    for m in call["messages"]:
        for b in m["content"]:
            assert "TOM TAT CU" not in str(b)
