import uuid

import pytest

from app.models import ChatRequest, ChatRequestStatus, Conversation, Role, User, Workspace
from app.services import continuity, presence


# --- is_resume_phrase ---

@pytest.mark.parametrize("text", [
    "tiếp tục công việc",
    "  Tiếp Tục  Công Việc ",
    "TIEP TUC CONG VIEC",
    "tiep tuc cong viec",
])
def test_is_resume_phrase_matches_variants(text):
    assert continuity.is_resume_phrase(text) is True


@pytest.mark.parametrize("text", [
    "tiếp tục",
    "làm nốt công việc",
    "tiếp tục công việc nhé",
    "",
])
def test_is_resume_phrase_rejects_other_text(text):
    assert continuity.is_resume_phrase(text) is False


# --- presence ---

def test_presence_counts_per_conversation():
    presence.reset()
    cid, other = uuid.uuid4(), uuid.uuid4()
    assert presence.connect(cid) == 1
    assert presence.connect(cid) == 2
    assert presence.connect(other) == 1  # conversation khác đếm riêng
    assert presence.disconnect(cid) == 1
    assert presence.disconnect(cid) == 0
    assert presence.disconnect(cid) == 0  # floor 0, không âm


# --- hold_queue_if_pending ---

async def _setup_conv(db):
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
    return ws, ceo, conv


@pytest.mark.asyncio
async def test_hold_queue_if_pending_sets_flag_when_queued(db_session):
    ws, ceo, conv = await _setup_conv(db_session)
    db_session.add(ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                               content="viec dang do", queue_position=1.0))
    await db_session.commit()

    held = await continuity.hold_queue_if_pending(db_session, conv.id)

    assert held is True
    await db_session.refresh(conv)
    assert conv.queue_held is True


@pytest.mark.asyncio
async def test_hold_queue_if_pending_sets_flag_when_running(db_session):
    ws, ceo, conv = await _setup_conv(db_session)
    db_session.add(ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                               content="dang chay", queue_position=1.0,
                               status=ChatRequestStatus.running))
    await db_session.commit()

    assert await continuity.hold_queue_if_pending(db_session, conv.id) is True


@pytest.mark.asyncio
async def test_hold_queue_if_pending_noop_when_queue_empty(db_session):
    ws, ceo, conv = await _setup_conv(db_session)
    db_session.add(ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                               content="da xong", queue_position=1.0,
                               status=ChatRequestStatus.done))
    await db_session.commit()

    held = await continuity.hold_queue_if_pending(db_session, conv.id)

    assert held is False
    await db_session.refresh(conv)
    assert conv.queue_held is False
