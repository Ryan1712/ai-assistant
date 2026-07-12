"""Push notification qua Expo Push API — đứng sau PushClient protocol.

Mặc định MockPushClient (settings.push_mock=True) để dev/test không gọi mạng;
ExpoPushClient bật khi deploy thật (cần app build dev-client/production).
"""
import uuid
from typing import Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Device

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

_TITLES = {
    "task_assigned": "Bạn được giao task mới",
    "task_update": "Task có cập nhật tiến độ",
    "account_locked": "Tài khoản của bạn đã bị khóa",
    "unlock_request": "Có yêu cầu mở khóa tài khoản",
}


class PushClient(Protocol):
    async def send(self, tokens: list[str], title: str, body: str, data: dict) -> None: ...


class MockPushClient:
    def __init__(self) -> None:
        self.sent: list[tuple[list[str], str, str, dict]] = []

    async def send(self, tokens: list[str], title: str, body: str, data: dict) -> None:
        self.sent.append((tokens, title, body, data))


class ExpoPushClient:
    async def send(self, tokens: list[str], title: str, body: str, data: dict) -> None:
        messages = [{"to": t, "title": title, "body": body, "data": data} for t in tokens]
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(EXPO_PUSH_URL, json=messages)


mock_push_client = MockPushClient()  # singleton để test inspect


def get_push_client() -> PushClient:
    if get_settings().push_mock:
        return mock_push_client
    return ExpoPushClient()


async def push_to_user(db: AsyncSession, recipient_id: uuid.UUID, type_: str,
                       payload: dict) -> None:
    """Bắn push tới mọi device có token của user. Best-effort — không bao giờ raise
    (push hỏng không được phá transaction nghiệp vụ)."""
    try:
        rows = await db.execute(select(Device.push_token).where(
            Device.user_id == recipient_id, Device.push_token.is_not(None),
        ))
        tokens = [t for t in rows.scalars() if t]
        if not tokens:
            return
        title = _TITLES.get(type_, "Thông báo mới")
        await get_push_client().send(tokens, title, "", {"type": type_, **payload})
    except Exception:
        pass


async def register_push_token(db: AsyncSession, actor, device_uuid: str,
                              push_token: str) -> None:
    device = (await db.execute(select(Device).where(
        Device.user_id == actor.id, Device.device_uuid == device_uuid,
    ))).scalar_one_or_none()
    if device is None:
        from fastapi import HTTPException
        raise HTTPException(404, "device_not_found")
    device.push_token = push_token
    await db.commit()
