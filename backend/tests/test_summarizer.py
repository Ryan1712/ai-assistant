import uuid
from datetime import datetime, timedelta, timezone

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta
from app.agent.summarizer import SUMMARY_KEEP_RECENT, maybe_compress_history
from app.models import Conversation, Message, MessageRole


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
