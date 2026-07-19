import uuid

from app.agent.loop import MAX_HISTORY_MESSAGES, _load_history
from app.models import ChatRequest, ChatRequestStatus, Conversation, Message, MessageRole


async def _mk_conv(db):
    ws, user = uuid.uuid4(), uuid.uuid4()
    conv = Conversation(workspace_id=ws, user_id=user)
    db.add(conv)
    await db.flush()
    return conv


async def _mk_req(db, conv, content, pos, status=ChatRequestStatus.queued):
    req = ChatRequest(workspace_id=conv.workspace_id, conversation_id=conv.id,
                      user_id=conv.user_id, content=content, queue_position=pos,
                      status=status)
    db.add(req)
    await db.flush()
    db.add(Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                   chat_request_id=req.id, role=MessageRole.user,
                   content=[{"type": "text", "text": content}]))
    return req


async def test_tin_queued_khac_khong_lot_vao_history(db_session):
    conv = await _mk_conv(db_session)
    req1 = await _mk_req(db_session, conv, "tin 1", 1.0)
    await _mk_req(db_session, conv, "tin 2 (cho xu ly)", 2.0)
    await db_session.commit()

    history = await _load_history(db_session, conv.id, req1.id)
    texts = [b["text"] for m in history for b in m["content"] if b.get("type") == "text"]
    assert "tin 1" in texts
    assert all("tin 2" not in t for t in texts)


async def test_tin_da_xong_van_trong_history(db_session):
    conv = await _mk_conv(db_session)
    await _mk_req(db_session, conv, "tin cu da xong", 1.0, status=ChatRequestStatus.done)
    req2 = await _mk_req(db_session, conv, "tin moi", 2.0)
    await db_session.commit()

    history = await _load_history(db_session, conv.id, req2.id)
    texts = [b["text"] for m in history for b in m["content"] if b.get("type") == "text"]
    assert "tin cu da xong" in texts and "tin moi" in texts


async def test_history_bi_cat_va_bat_dau_bang_user_text(db_session):
    conv = await _mk_conv(db_session)
    req = None
    for i in range(MAX_HISTORY_MESSAGES + 20):
        req = await _mk_req(db_session, conv, f"tin {i}", float(i),
                            status=ChatRequestStatus.done)
        db_session.add(Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                               chat_request_id=req.id, role=MessageRole.assistant,
                               content=[{"type": "text", "text": f"tra loi {i}"}]))
    await db_session.commit()

    history = await _load_history(db_session, conv.id, req.id)
    assert len(history) <= MAX_HISTORY_MESSAGES
    first = history[0]
    assert first["role"] == "user"
    assert first["content"][0]["type"] == "text"
