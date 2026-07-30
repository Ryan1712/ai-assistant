"""Tự đặt tên cuộc trò chuyện bằng AI (model_fast), sau khi AI trả lời xong tin đầu.

`maybe_generate_title` được gọi TRỰC TIẾP từ app/agent/worker.py sau MỌI lượt chat
(không chỉ lượt đầu — worker.py không biết đây có phải lượt đầu hay không), nhưng
tự giới hạn CHỈ THỬ Ở LƯỢT ĐẦU TIÊN của conversation (không còn cron nền — bỏ
2026-07-30: cron mỗi phút quét title_locked=False từng khiến 1 conversation lỗi
gọi LLM 1 lần bị thử lại VÔ HẠN, mỗi phút, kể cả khi không ai dùng app — tốn
credit LLM gateway hàng nghìn lần/ngày ngoài ý muốn).

Edge case tìm thấy sau khi bỏ cron (cùng ngày): nếu KHÔNG giới hạn ở lượt đầu, và
LLM lỗi kéo dài (vd hết tiền), mỗi lượt chat tiếp theo của user trong CÙNG
conversation sẽ lại thử gọi LLM đặt tên — nhẹ hơn bug cron cũ (bị chặn bởi hành vi
user thật, không phải vô hạn tự động) nhưng vẫn lãng phí. Nên chỉ thử ĐÚNG 1 LẦN
DUY NHẤT/conversation — lỗi thì bỏ qua vĩnh viễn (giữ title tạm), không phải chỉ
"tạm thời tới lượt sau".

`retitle_pending_conversations` (sweep theo batch) vẫn giữ lại cho mục đích khác:
backfill title cho conversation cũ tạo trước khi cơ chế này tồn tại. Không còn cron
nào gọi nó tự động — chỉ dùng thủ công/script nếu cần.
"""
from __future__ import annotations

import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm_client import LLMClient, TextDelta
from app.models import ChatRequest, ChatRequestStatus, Conversation, Message, MessageRole

logger = logging.getLogger(__name__)

_TITLE_SYSTEM = (
    "Đặt 1 tiêu đề NGẮN GỌN (tối đa 6 từ, tiếng Việt, không bọc trong dấu ngoặc kép, "
    "không có dấu chấm cuối câu) tóm tắt đúng chủ đề chính của đoạn hội thoại dưới "
    "đây, để hiển thị trong danh sách cuộc trò chuyện. Chỉ trả về đúng tiêu đề, "
    "không thêm lời dẫn hay giải thích."
)


def _render_for_title(msgs: list[Message]) -> str:
    lines: list[str] = []
    for m in msgs:
        who = "Người dùng" if m.role == MessageRole.user else "Trợ lý"
        texts = [b.get("text", "") for b in m.content if b.get("type") == "text"]
        if texts:
            lines.append(f"{who}: {' '.join(t for t in texts if t)}")
    return "\n".join(lines)


async def _generate_title(llm: LLMClient, transcript: str) -> str:
    parts: list[str] = []
    async for event in llm.stream(
        system=_TITLE_SYSTEM,
        messages=[{"role": "user", "content": [{"type": "text", "text": transcript}]}],
        tools=[]):
        if isinstance(event, TextDelta):
            parts.append(event.text)
    return "".join(parts).strip().strip('"').strip("'")[:60]


async def retitle_pending_conversations(db: AsyncSession, llm: LLMClient, *,
                                        batch_size: int = 10) -> int:
    """Sinh tiêu đề cho tối đa `batch_size` conversation có AI trả lời nhưng chưa
    `title_locked`. Trả về số conversation đã xử lý thành công. Lỗi gọi LLM cho 1
    conversation không chặn các conversation khác trong cùng lượt (best-effort —
    conversation lỗi vẫn giữ `title_locked=False`, cron lượt sau tự thử lại)."""
    id_stmt = (
        select(Conversation.id)
        .join(Message, Message.conversation_id == Conversation.id)
        .where(Conversation.title_locked.is_(False), Message.role == MessageRole.assistant)
        .distinct()
        .limit(batch_size)
    )
    conv_ids = (await db.execute(id_stmt)).scalars().all()
    if not conv_ids:
        return 0
    conversations = (await db.execute(
        select(Conversation).where(Conversation.id.in_(conv_ids)))).scalars().all()

    processed = 0
    for conv in conversations:
        msgs = (await db.execute(
            select(Message).where(Message.conversation_id == conv.id)
            .order_by(Message.created_at.asc()).limit(4))).scalars().all()
        transcript = _render_for_title(msgs)
        if not transcript:
            continue
        try:
            title = await _generate_title(llm, transcript)
        except Exception:
            logger.warning("retitle_pending_conversations: lỗi gọi LLM cho conversation %s, "
                           "bỏ qua lượt này", conv.id)
            continue
        if not title:
            continue
        # Fix (whole-branch review, race với PATCH rename thủ công): KHÔNG gán
        # attribute ORM rồi commit gộp 1 lần cuối vòng lặp — nếu người dùng tự đổi
        # tên (title_locked=True, session/transaction KHÁC) trong lúc batch này còn
        # đang chạy (LLM call có thể mất vài giây/conversation), commit gộp cuối
        # cùng sẽ vô tình đè lên tên vừa đổi. UPDATE có điều kiện + commit ngay
        # sau MỖI conversation giữ cho quyết định "có ghi hay không" atomic và cửa
        # sổ race hẹp nhất có thể (chỉ còn giữa lúc SELECT candidate và UPDATE này).
        result = await db.execute(
            update(Conversation)
            .where(Conversation.id == conv.id, Conversation.title_locked.is_(False))
            .values(title=title, title_locked=True))
        await db.commit()
        if result.rowcount:
            processed += 1
    return processed


async def maybe_generate_title(db: AsyncSession, conv: Conversation | None,
                               llm: LLMClient) -> None:
    """Đặt tên MỘT LẦN DUY NHẤT ở lượt chat đầu tiên — gọi từ worker.py sau MỌI
    lượt (worker không biết đây có phải lượt đầu), tự giới hạn bằng cách đếm
    ChatRequest không còn queued: >=2 nghĩa là đã qua lượt đầu, không thử lại nữa
    dù title_locked vẫn False (tránh edge case gọi LLM thừa mỗi lượt chat khi lỗi
    kéo dài — xem module docstring). Best-effort: lỗi gọi LLM thì giữ nguyên title
    tạm (60 ký tự đầu tin nhắn, gán sẵn ở send_message) và title_locked=False,
    KHÔNG tự retry — không còn cron nào lặp lại việc này."""
    if conv is None or conv.title_locked:
        return
    past_requests = (await db.execute(
        select(ChatRequest.id).where(
            ChatRequest.conversation_id == conv.id,
            ChatRequest.status != ChatRequestStatus.queued,
        ).limit(2))).scalars().all()
    if len(past_requests) >= 2:
        return
    msgs = (await db.execute(
        select(Message).where(Message.conversation_id == conv.id)
        .order_by(Message.created_at.asc()).limit(4))).scalars().all()
    if not any(m.role == MessageRole.assistant for m in msgs):
        return
    transcript = _render_for_title(msgs)
    if not transcript:
        return
    try:
        title = await _generate_title(llm, transcript)
    except Exception:
        logger.warning("maybe_generate_title: lỗi gọi LLM cho conversation %s, "
                       "giữ title tạm", conv.id)
        return
    if not title:
        return
    result = await db.execute(
        update(Conversation)
        .where(Conversation.id == conv.id, Conversation.title_locked.is_(False))
        .values(title=title, title_locked=True))
    await db.commit()
    if result.rowcount:
        conv.title = title
        conv.title_locked = True
