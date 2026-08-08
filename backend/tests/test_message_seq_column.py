import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models import Conversation, Message, MessageRole


async def _mk_conv(db):
    ws, user = uuid.uuid4(), uuid.uuid4()
    conv = Conversation(workspace_id=ws, user_id=user)
    db.add(conv)
    await db.flush()
    return conv


@pytest.mark.asyncio
async def test_message_seq_auto_increments_even_with_same_created_at(db_session):
    """seq phai tang dan dung THU TU INSERT that, ke ca khi created_at TRUNG
    NHAU giua nhieu Message (rat de xay ra: assistant tra loi + tool_result
    ghi gan nhu dong thoi trong cung 1 request) -- tie-break cu bang Message.id
    (UUID ngau nhien) co the dao lon thu tu nay (xem
    app/agent/loop.py::_merge_consecutive_roles va bug that da tim ra qua
    test_load_history_gop_2_message_role_giong_nhau_lien_nhau)."""
    conv = await _mk_conv(db_session)
    same_ts = datetime.now(timezone.utc)
    m1 = Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                 role=MessageRole.user, content=[{"type": "text", "text": "a"}],
                 created_at=same_ts)
    db_session.add(m1)
    await db_session.flush()
    m2 = Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                 role=MessageRole.assistant, content=[{"type": "text", "text": "b"}],
                 created_at=same_ts)
    db_session.add(m2)
    await db_session.flush()
    m3 = Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                 role=MessageRole.user, content=[{"type": "text", "text": "c"}],
                 created_at=same_ts)
    db_session.add(m3)
    await db_session.commit()

    rows = (await db_session.execute(
        select(Message).where(Message.conversation_id == conv.id).order_by(Message.seq.asc())
    )).scalars().all()
    assert [r.content[0]["text"] for r in rows] == ["a", "b", "c"]
    assert rows[0].seq < rows[1].seq < rows[2].seq
