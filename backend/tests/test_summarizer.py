import uuid
from datetime import datetime, timedelta, timezone

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta
from app.agent.summarizer import SUMMARY_KEEP_RECENT, maybe_compress_history
from app.models import (
    ChatRequest, ChatRequestStatus, Conversation, Message, MessageRole, User, Workspace,
)


async def test_conversation_co_cot_session_model_defaults(db_session):
    conv = Conversation(workspace_id=uuid.uuid4(), user_id=uuid.uuid4())
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)
    assert conv.rolling_summary == ""
    assert conv.summary_through_at is None
    assert conv.archived_at is None


async def _mk_conv(db):
    conv = Conversation(workspace_id=uuid.uuid4(), user_id=uuid.uuid4())
    db.add(conv)
    await db.flush()
    return conv


def _fake_summary_llm(text="TOM TAT: chot deadline X ngay 30, giao Duy task Y"):
    return FakeLLMClient(turns=[[TextDelta(text=text),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)]])


def _aware(dt):
    # SQLite (test) tra ve naive du cot khai bao DateTime(timezone=True) - gia tri
    # luon la UTC (bai hoc da ghi trong project memory: "bay SQLite timezone khi
    # viet test period-bounds"; xem cung pattern o analytics_service._aware).
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def test_khong_nen_qua_message_cua_request_chua_chay(db_session):
    """Bug: gửi R2 lúc R1 đang chạy nặng → R1 sinh nhiều message SAU (created_at
    lớn hơn) message của R2. Nếu summarizer fold cả message R2 (queued) thì
    summary_through_at vượt qua nó → _load_history (created_at > watermark) BỎ LUÔN
    câu hỏi của chính R2 khi R2 chạy → model trả lời nhầm. Watermark KHÔNG được
    vượt qua message của bất kỳ request chưa chạy nào."""
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    user = User(workspace_id=ws.id, email="u@a.vn", password_hash="x", full_name="U",
                role="ceo", is_root=True)
    db_session.add(user)
    await db_session.flush()
    conv = Conversation(workspace_id=ws.id, user_id=user.id)
    db_session.add(conv)
    await db_session.flush()
    r1 = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=user.id,
                     content="R1", queue_position=1.0, status=ChatRequestStatus.running)
    r2 = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=user.id,
                     content="cau hoi R2 quan trong", queue_position=2.0,
                     status=ChatRequestStatus.queued)
    db_session.add_all([r1, r2])
    await db_session.flush()

    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # R1 user msg tại t0
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=r1.id,
                           role=MessageRole.user, content=[{"type": "text", "text": "R1"}],
                           created_at=base))
    # R2 user msg tại t1 (user gửi khi R1 mới chạy)
    r2_at = base + timedelta(minutes=1)
    db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=r2.id,
                           role=MessageRole.user,
                           content=[{"type": "text", "text": "cau hoi R2 quan trong"}],
                           created_at=r2_at))
    # R1 sinh 70 message SAU R2 (t2..t71) — đủ vượt trigger, đẩy cut qua mốc R2
    for i in range(70):
        role = MessageRole.user if i % 2 == 0 else MessageRole.assistant
        db_session.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=r1.id,
                               role=role, content=[{"type": "text", "text": f"R1 buoc {i}"}],
                               created_at=base + timedelta(minutes=2 + i)))
    await db_session.commit()

    llm = _fake_summary_llm()
    changed = await maybe_compress_history(db_session, conv, llm)
    await db_session.refresh(conv)

    assert changed is True
    # Watermark PHẢI nằm TRƯỚC message của R2 — để _load_history của R2 còn thấy nó.
    assert _aware(conv.summary_through_at) < r2_at


async def test_nen_khi_vuot_trigger(db_session):
    conv = await _mk_conv(db_session)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(70):  # > SUMMARY_TRIGGER(60)
        role = MessageRole.user if i % 2 == 0 else MessageRole.assistant
        db_session.add(Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                               role=role, content=[{"type": "text", "text": f"tin {i}"}],
                               created_at=base + timedelta(minutes=i)))
    await db_session.commit()

    llm = _fake_summary_llm()
    changed = await maybe_compress_history(db_session, conv, llm)
    await db_session.refresh(conv)
    assert changed is True
    assert "TOM TAT" in conv.rolling_summary
    assert conv.summary_through_at is not None
    # mốc phải nằm ở message thứ (70 - KEEP_RECENT) trở về trước
    assert _aware(conv.summary_through_at) <= base + timedelta(minutes=70 - SUMMARY_KEEP_RECENT)


async def test_khong_nen_khi_duoi_trigger(db_session):
    conv = await _mk_conv(db_session)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(10):
        db_session.add(Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                               role=MessageRole.user, content=[{"type": "text", "text": f"t{i}"}],
                               created_at=base + timedelta(minutes=i)))
    await db_session.commit()
    llm = _fake_summary_llm()
    changed = await maybe_compress_history(db_session, conv, llm)
    assert changed is False
    assert llm.calls == []  # khong goi LLM khi duoi nguong


async def test_force_nen_toan_bo_du_it(db_session):
    conv = await _mk_conv(db_session)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(5):
        role = MessageRole.user if i % 2 == 0 else MessageRole.assistant
        db_session.add(Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                               role=role, content=[{"type": "text", "text": f"t{i}"}],
                               created_at=base + timedelta(minutes=i)))
    await db_session.commit()
    llm = _fake_summary_llm("TOM TAT NGAN")
    changed = await maybe_compress_history(db_session, conv, llm, force=True, keep_recent=0)
    await db_session.refresh(conv)
    assert changed is True
    assert conv.rolling_summary == "TOM TAT NGAN"
    assert _aware(conv.summary_through_at) == base + timedelta(minutes=4)  # message cuoi


async def test_ack_va_rong_khong_tinh(db_session):
    conv = await _mk_conv(db_session)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db_session.add(Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                           role=MessageRole.assistant, content=[{"type": "text", "text": "ack"}],
                           is_ack=True, created_at=base))
    await db_session.commit()
    llm = _fake_summary_llm()
    changed = await maybe_compress_history(db_session, conv, llm, force=True, keep_recent=0)
    assert changed is False  # chi co 1 ack -> khong co gi de nen


async def test_seed_only_khong_bi_nen(db_session):
    conv = await _mk_conv(db_session)
    db_session.add(Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                           role=MessageRole.assistant, is_seed=True,
                           content=[{"type": "text", "text": "Chao mung!"}]))
    await db_session.commit()
    llm = _fake_summary_llm()
    changed = await maybe_compress_history(db_session, conv, llm, force=True, keep_recent=0)
    assert changed is False
    assert llm.calls == []
