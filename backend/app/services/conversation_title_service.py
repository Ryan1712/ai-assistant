"""Tự đặt tên cuộc trò chuyện bằng AI (model_fast), sau khi AI trả lời xong tin đầu.

Chạy từ cron (app/agent/worker.py::retitle_conversations, mỗi phút). Quét tối đa
`batch_size` cuộc/lượt để tránh dồn cục chi phí LLM ngay sau khi deploy — sweep toàn
bộ lịch sử cũ trải dần qua nhiều lượt cron (spec 2026-07-27 §2.4).
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm_client import LLMClient, TextDelta
from app.models import Conversation, Message, MessageRole

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
        conv.title = title
        conv.title_locked = True
        processed += 1
    await db.commit()
    return processed
