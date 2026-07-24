"""Phase 5 (session model): active conversation + xoay conversation ngầm.

Bất biến: mỗi user có ≤1 conversation "sống" (archived_at IS NULL, mới nhất). Xoay
khi idle > ROTATE_IDLE_HOURS HOẶC > ROTATE_MAX_MESSAGES message sống, nhưng KHÔNG
xoay nếu còn việc dang dở (queue). Resolve lúc FE mount qua GET /conversations/active.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm_client import LLMClient
from app.agent.summarizer import maybe_compress_history
from app.models import ChatRequest, ChatRequestStatus, Conversation, Message, User

ROTATE_IDLE_HOURS = 12
ROTATE_MAX_MESSAGES = 150

_BUSY_STATUSES = [
    ChatRequestStatus.queued, ChatRequestStatus.running,
    ChatRequestStatus.deep_running, ChatRequestStatus.awaiting_confirmation,
]


def _as_aware(dt: datetime) -> datetime:
    """SQLite trả datetime naive — chuẩn hóa về aware/UTC trước khi so (bài học period-bounds)."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


async def _active_conv(db: AsyncSession, actor: User) -> Conversation | None:
    return (await db.execute(select(Conversation).where(
        Conversation.workspace_id == actor.workspace_id,
        Conversation.user_id == actor.id,
        Conversation.archived_at.is_(None),
    ).order_by(Conversation.created_at.desc()).limit(1))).scalar_one_or_none()


async def get_or_rotate_active_conversation(
        db: AsyncSession, actor: User,
        llm_factory: Callable[[], LLMClient], *,
        now: datetime | None = None) -> Conversation:
    now = _as_aware(now) if now is not None else datetime.now(timezone.utc)
    conv = await _active_conv(db, actor)
    if conv is None:
        conv = Conversation(workspace_id=actor.workspace_id, user_id=actor.id)
        db.add(conv)
        await db.commit()
        return conv

    # Còn việc dang dở -> không xoay (tránh bỏ rơi queue).
    busy = (await db.execute(select(ChatRequest.id).where(
        ChatRequest.conversation_id == conv.id,
        ChatRequest.status.in_(_BUSY_STATUSES),
    ).limit(1))).scalar_one_or_none()
    if busy is not None or conv.queue_held:
        return conv

    live = [m for m in (await db.execute(select(Message).where(
        Message.conversation_id == conv.id, Message.is_ack.is_(False),
    ).order_by(Message.created_at.asc(), Message.id.asc()))).scalars().all() if m.content]
    count = len(live)
    last_at = _as_aware(live[-1].created_at) if live else _as_aware(conv.created_at)
    idle = (now - last_at) > timedelta(hours=ROTATE_IDLE_HOURS)
    too_big = count > ROTATE_MAX_MESSAGES
    if not (idle or too_big):
        return conv

    # Xoay: fold toàn bộ đuôi vào summary conv cũ -> seed conv mới -> archive conv cũ.
    await maybe_compress_history(db, conv, llm_factory(), force=True, keep_recent=0)
    conv.archived_at = now
    new = Conversation(workspace_id=actor.workspace_id, user_id=actor.id,
                       rolling_summary=conv.rolling_summary)
    db.add(new)
    await db.commit()
    return new
