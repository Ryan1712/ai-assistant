import uuid

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta
from app.models import Conversation, Message, MessageRole
from app.services.conversation_title_service import (
    maybe_generate_title, retitle_pending_conversations,
)


def _fake_title_llm(text="Giao task quy 3 cho Nam"):
    return FakeLLMClient(turns=[[TextDelta(text=text),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)]])


async def _mk_conv_with_reply(db, *, title_locked=False,
                              title="tin nhan dau tien cat 60 ky tu"):
    conv = Conversation(workspace_id=uuid.uuid4(), user_id=uuid.uuid4(),
                        title=title, title_locked=title_locked)
    db.add(conv)
    await db.flush()
    db.add(Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                   role=MessageRole.user, content=[{"type": "text", "text": "giao task cho Nam"}]))
    db.add(Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                   role=MessageRole.assistant, content=[{"type": "text", "text": "Da tao task"}]))
    await db.commit()
    return conv


async def test_retitle_sets_title_and_locks(db_session):
    conv = await _mk_conv_with_reply(db_session)
    llm = _fake_title_llm("Giao task quy 3 cho Nam")

    processed = await retitle_pending_conversations(db_session, llm)

    assert processed == 1
    await db_session.refresh(conv)
    assert conv.title == "Giao task quy 3 cho Nam"
    assert conv.title_locked is True
    assert len(llm.calls) == 1


async def test_retitle_bo_qua_conversation_da_locked(db_session):
    conv = await _mk_conv_with_reply(db_session, title_locked=True)
    llm = _fake_title_llm()

    processed = await retitle_pending_conversations(db_session, llm)

    assert processed == 0
    assert len(llm.calls) == 0
    await db_session.refresh(conv)
    assert conv.title == "tin nhan dau tien cat 60 ky tu"


async def test_retitle_bo_qua_conversation_chua_co_ai_tra_loi(db_session):
    conv = Conversation(workspace_id=uuid.uuid4(), user_id=uuid.uuid4(), title="cho AI tra loi")
    db_session.add(conv)
    await db_session.flush()
    db_session.add(Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                           role=MessageRole.user, content=[{"type": "text", "text": "hoi gi do"}]))
    await db_session.commit()
    llm = _fake_title_llm()

    processed = await retitle_pending_conversations(db_session, llm)

    assert processed == 0
    await db_session.refresh(conv)
    assert conv.title == "cho AI tra loi"


async def test_retitle_gioi_han_batch_size(db_session):
    for _ in range(3):
        await _mk_conv_with_reply(db_session)
    llm = FakeLLMClient(turns=[
        [TextDelta(text=f"Tieu de {i}"),
         StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)]
        for i in range(2)
    ])

    processed = await retitle_pending_conversations(db_session, llm, batch_size=2)

    assert processed == 2


async def test_retitle_khong_ghi_de_manual_rename_xay_ra_giua_batch(db_session):
    """Fix 2 (whole-branch review): trước đây conversation_title_service ghi
    conv.title/title_locked bằng attribute assignment ORM thường rồi chỉ commit
    1 LẦN ở cuối vòng lặp — nếu người dùng PATCH rename (title_locked=True) 1
    conversation đang nằm trong batch trong lúc batch còn chạy (LLM call có thể
    mất vài giây), commit cuối lượt sẽ ghi đè object cũ trong session đè lên tên
    người dùng vừa đặt. Test này giả lập race bằng cách tự set title_locked=True
    (qua UPDATE riêng, giống PATCH /conversations/{id}) SAU khi hàm đã build xong
    candidate list (mô phỏng bằng cách patch app.services.conversation_title_service
    để chèn hành động đó ngay trước khi service ghi kết quả) — với fix dùng
    update(...).where(title_locked.is_(False)) + commit từng conversation, UPDATE
    này sẽ apply 0 dòng nên tên thủ công của người dùng phải sống sót."""
    from sqlalchemy import update as sa_update

    from app.services import conversation_title_service

    conv = await _mk_conv_with_reply(db_session)
    manual_title = "Ten nguoi dung tu doi tay"

    class _RaceLLM:
        model = "fake"

        def __init__(self):
            self.calls = []

        async def stream(self, *, system, messages, tools):
            # Mô phỏng: giữa lúc build xong candidate list và lúc service ghi kết
            # quả (đây là khoảng "LLM call mất vài giây" theo mô tả root cause),
            # 1 request khác (PATCH rename) commit riêng title_locked=True.
            self.calls.append(1)
            await db_session.execute(
                sa_update(Conversation).where(Conversation.id == conv.id)
                .values(title=manual_title, title_locked=True))
            await db_session.commit()
            yield TextDelta(text="Tieu de AI dat")
            yield StreamDone(tool_uses=[], stop_reason="end_turn",
                             input_tokens=1, output_tokens=1)

    llm = _RaceLLM()

    processed = await conversation_title_service.retitle_pending_conversations(db_session, llm)

    assert processed == 0  # UPDATE có điều kiện title_locked.is_(False) áp dụng 0 dòng
    await db_session.refresh(conv)
    assert conv.title == manual_title
    assert conv.title_locked is True


async def test_retitle_loi_llm_khong_lock_thu_lai_luot_sau(db_session, monkeypatch):
    conv = await _mk_conv_with_reply(db_session)

    class _BoomLLM:
        model = "fake"
        calls: list = []

        async def stream(self, *, system, messages, tools):
            raise RuntimeError("gateway loi")
            yield  # pragma: no cover - làm hàm thành async generator hợp lệ

    processed = await retitle_pending_conversations(db_session, _BoomLLM())

    assert processed == 0
    await db_session.refresh(conv)
    assert conv.title_locked is False


async def test_maybe_generate_title_dat_ten_va_lock_ngay_sau_luot_dau(db_session):
    """Thay cron quét mỗi phút (đã bỏ vì retry vô hạn tốn LLM call — xem
    feedback 2026-07-30): đặt tên NGAY, gọi 1 lần duy nhất từ worker.py sau khi
    run_agent_loop/run_deep_ack_turn hoàn tất lượt đầu tiên."""
    conv = await _mk_conv_with_reply(db_session)
    llm = _fake_title_llm("Giao task quy 3 cho Nam")

    await maybe_generate_title(db_session, conv, llm)

    await db_session.refresh(conv)
    assert conv.title == "Giao task quy 3 cho Nam"
    assert conv.title_locked is True
    assert len(llm.calls) == 1


async def test_maybe_generate_title_bo_qua_conversation_da_locked(db_session):
    conv = await _mk_conv_with_reply(db_session, title_locked=True)
    llm = _fake_title_llm()

    await maybe_generate_title(db_session, conv, llm)

    assert len(llm.calls) == 0
    await db_session.refresh(conv)
    assert conv.title == "tin nhan dau tien cat 60 ky tu"


async def test_maybe_generate_title_bo_qua_conversation_chua_co_ai_tra_loi(db_session):
    conv = Conversation(workspace_id=uuid.uuid4(), user_id=uuid.uuid4(), title="cho AI tra loi")
    db_session.add(conv)
    await db_session.flush()
    db_session.add(Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                           role=MessageRole.user, content=[{"type": "text", "text": "hoi gi do"}]))
    await db_session.commit()
    llm = _fake_title_llm()

    await maybe_generate_title(db_session, conv, llm)

    assert len(llm.calls) == 0
    await db_session.refresh(conv)
    assert conv.title == "cho AI tra loi"


async def test_maybe_generate_title_loi_llm_giu_nguyen_title_tam_khong_lock(db_session):
    """Best-effort — lỗi gọi LLM thì GIỮ NGUYÊN title tạm 60 ký tự đã có sẵn từ
    send_message, KHÔNG lock. Không còn cron thử lại vô hạn nữa: cơ hội thử lại
    tiếp theo (nếu có) chỉ tới khi user thật sự nhắn thêm 1 lượt chat mới —
    không phải cron nền chạy mỗi phút bất kể có ai dùng app hay không."""
    conv = await _mk_conv_with_reply(db_session)

    class _BoomLLM:
        model = "fake"

        async def stream(self, *, system, messages, tools):
            raise RuntimeError("gateway loi")
            yield  # pragma: no cover - làm hàm thành async generator hợp lệ

    await maybe_generate_title(db_session, conv, _BoomLLM())

    await db_session.refresh(conv)
    assert conv.title == "tin nhan dau tien cat 60 ky tu"
    assert conv.title_locked is False


async def test_maybe_generate_title_conv_none_khong_lam_gi(db_session):
    """worker.py có thể gọi với conv=None (route hiếm/edge) — không được raise."""
    llm = _fake_title_llm()

    await maybe_generate_title(db_session, None, llm)

    assert len(llm.calls) == 0
