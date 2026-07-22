"""'Tiếp tục công việc' (funtional-plan 5.7).

Mất mạng / đóng app (socket cuối cùng của conversation đóng) → hold toàn bộ
queue của conversation đó (`conversations.queue_held`). Worker dừng xử lý khi
held; chỉ tin nhắn khớp cụm "tiếp tục công việc" mới clear cờ (xem
app/api/chat.py::send_message). Reconnect KHÔNG tự resume — chủ đích spec.
"""
import unicodedata
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChatRequest, ChatRequestStatus, Conversation

RESUME_PHRASE = "tiep tuc cong viec"


def normalize_vn(text: str) -> str:
    """casefold + đ→d + bỏ dấu (NFD, bỏ combining marks) + gộp khoảng trắng — dùng
    chung cho match cụm resume-phrase (ở đây) và fuzzy person/task (fuzzy_match.py)."""
    text = text.casefold().replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.split())


def is_resume_phrase(text: str) -> bool:
    return normalize_vn(text) == RESUME_PHRASE


async def hold_queue_if_pending(db: AsyncSession, conversation_id: uuid.UUID) -> bool:
    """Set queue_held nếu conversation còn việc dang dở (queued/running).

    Trả về True nếu đã hold. Queue rỗng → không set (không có gì để 'làm nốt').
    """
    pending = (await db.execute(
        select(ChatRequest.id).where(
            ChatRequest.conversation_id == conversation_id,
            ChatRequest.status.in_([ChatRequestStatus.queued, ChatRequestStatus.running]),
        ).limit(1)
    )).scalar_one_or_none()
    if pending is None:
        return False
    conv = await db.get(Conversation, conversation_id)
    if conv is None:
        return False
    conv.queue_held = True
    await db.commit()
    return True
