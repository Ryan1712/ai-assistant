from __future__ import annotations

import uuid
from typing import AsyncIterator, Awaitable, Callable

import jwt
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.agent.publisher import EventPublisher, get_event_publisher
from app.db import get_db
from app.models import Conversation
from app.services import presence

router = APIRouter()


class WebSocketAuthError(Exception):
    pass


async def authorize_ws(db: AsyncSession, token: str, conversation_id: uuid.UUID) -> Conversation:
    """Giải mã token + xác nhận conversation thuộc đúng user/workspace.
    Raise WebSocketAuthError nếu bất kỳ bước nào không hợp lệ."""
    try:
        payload = security.decode_access_token(token)
        user_id = uuid.UUID(payload["sub"])
        workspace_id = uuid.UUID(payload["ws"])
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise WebSocketAuthError("invalid_token") from exc
    conv = await db.get(Conversation, conversation_id)
    if conv is None or conv.workspace_id != workspace_id or conv.user_id != user_id:
        raise WebSocketAuthError("conversation_not_found")
    return conv


async def stream_events(send_json: Callable[[dict], Awaitable[None]],
                        subscription: AsyncIterator[dict]) -> None:
    """Chuyển tiếp event từ subscription ra send_json — hàm thuần, test không cần WebSocket thật."""
    async for event in subscription:
        await send_json(event)


@router.websocket("/ws/conversations/{conversation_id}")
async def conversation_ws(
    websocket: WebSocket, conversation_id: uuid.UUID, token: str = Query(...),
    db: AsyncSession = Depends(get_db),
    publisher: EventPublisher = Depends(get_event_publisher),
):
    try:
        await authorize_ws(db, token, conversation_id)
    except WebSocketAuthError:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    presence.connect(conversation_id)
    try:
        await stream_events(websocket.send_json, publisher.subscribe(conversation_id))
    except WebSocketDisconnect:
        pass
    finally:
        presence.disconnect(conversation_id)
        # KHÔNG hold queue khi socket đóng nữa: trên mobile, rời màn chat/khóa máy
        # là đóng WS — hold ở đây làm AI "tự treo" giữa chừng việc dài, người dùng
        # tưởng lỗi. Việc dang dở cứ chạy nốt; kết quả lưu DB, mở lại màn là thấy.
        # Cờ queue_held + cụm "tiếp tục công việc" giữ nguyên cho conversation đã
        # held từ trước (dữ liệu cũ).
