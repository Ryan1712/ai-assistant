import uuid
from datetime import datetime, timedelta, timezone

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta
from app.models import (
    ChatRequest, ChatRequestStatus, Conversation, Message, MessageRole, Role, User, Workspace,
)
from app.services.session_service import (
    ROTATE_MAX_MESSAGES, get_or_rotate_active_conversation,
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


def _fake_llm():
    return FakeLLMClient(turns=[[TextDelta(text="SEED SUMMARY"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)]])


async def test_tao_moi_khi_chua_co(db_session):
    ws, ceo = await _seed(db_session)
    conv = await get_or_rotate_active_conversation(db_session, ceo, _fake_llm)
    assert conv.id is not None
    assert conv.archived_at is None


async def test_tra_lai_conv_song_khi_chua_can_xoay(db_session):
    ws, ceo = await _seed(db_session)
    existing = Conversation(workspace_id=ws.id, user_id=ceo.id)
    db_session.add(existing)
    await db_session.commit()
    now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    conv = await get_or_rotate_active_conversation(db_session, ceo, _fake_llm, now=now)
    assert conv.id == existing.id


async def test_xoay_khi_idle_qua_12h(db_session):
    ws, ceo = await _seed(db_session)
    old_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id, created_at=old_time)
    db_session.add(conv)
    await db_session.flush()
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, role=MessageRole.user,
                           content=[{"type": "text", "text": "hom qua dan viec X"}],
                           created_at=old_time))
    await db_session.commit()
    now = old_time + timedelta(hours=13)  # idle > 12h
    llm = _fake_llm()
    new = await get_or_rotate_active_conversation(db_session, ceo, lambda: llm, now=now)
    await db_session.refresh(conv)
    assert new.id != conv.id
    assert conv.archived_at is not None
    assert new.rolling_summary == "SEED SUMMARY"  # seed tu summary conv cu (da fold tail)


async def test_xoay_khi_qua_150_message(db_session):
    ws, ceo = await _seed(db_session)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id, created_at=base)
    db_session.add(conv)
    await db_session.flush()
    for i in range(ROTATE_MAX_MESSAGES + 2):
        db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, role=MessageRole.user,
                               content=[{"type": "text", "text": f"m{i}"}],
                               created_at=base + timedelta(seconds=i)))
    await db_session.commit()
    now = base + timedelta(seconds=200)  # chua idle
    new = await get_or_rotate_active_conversation(db_session, ceo, lambda: _fake_llm(), now=now)
    await db_session.refresh(conv)
    assert new.id != conv.id
    assert conv.archived_at is not None


async def test_khong_xoay_khi_con_viec_dang_do(db_session):
    ws, ceo = await _seed(db_session)
    old_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id, created_at=old_time)
    db_session.add(conv)
    await db_session.flush()
    db_session.add(ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                               content="dang cho", queue_position=1.0,
                               status=ChatRequestStatus.queued))
    await db_session.commit()
    now = old_time + timedelta(hours=20)  # idle nhung con viec queued
    conv2 = await get_or_rotate_active_conversation(db_session, ceo, _fake_llm, now=now)
    assert conv2.id == conv.id  # khong xoay
    await db_session.refresh(conv)
    assert conv.archived_at is None


async def test_rotation_nen_loi_khong_giet_request_tra_ve_conv_cu(db_session, monkeypatch):
    ws, ceo = await _seed(db_session)
    old_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id, created_at=old_time)
    db_session.add(conv)
    await db_session.flush()
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, role=MessageRole.user,
                           content=[{"type": "text", "text": "hom qua dan viec X"}],
                           created_at=old_time))
    await db_session.commit()
    now = old_time + timedelta(hours=13)  # idle > 12h -> would rotate

    async def _boom(*a, **k):
        raise RuntimeError("nen loi gia lap")
    monkeypatch.setattr("app.services.session_service.maybe_compress_history", _boom)

    result = await get_or_rotate_active_conversation(db_session, ceo, lambda: None, now=now)
    assert result.id == conv.id  # KHONG xoay - tra ve conv cu, khong crash
    await db_session.refresh(conv)
    assert conv.archived_at is None  # chua bi archive vi nen that bai


async def test_khong_lo_conv_user_khac(db_session):
    ws, ceo = await _seed(db_session)
    other = User(workspace_id=ws.id, email="o@a.vn", password_hash="x", full_name="O",
                 role=Role.manager)
    db_session.add(other)
    await db_session.flush()
    db_session.add(Conversation(workspace_id=ws.id, user_id=other.id))
    await db_session.commit()
    conv = await get_or_rotate_active_conversation(db_session, ceo, _fake_llm)
    assert conv.user_id == ceo.id
