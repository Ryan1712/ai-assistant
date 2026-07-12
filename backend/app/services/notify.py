"""Helper tập trung: ghi Notification (in-app) + bắn push best-effort.
Mọi chỗ tạo thông báo dùng hàm này thay vì db.add(Notification(...)) trực tiếp."""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification
from app.services import push_service


async def notify(db: AsyncSession, *, workspace_id: uuid.UUID, recipient_id: uuid.UUID,
                 type: str, payload: dict) -> Notification:
    n = Notification(workspace_id=workspace_id, recipient_id=recipient_id,
                     type=type, payload=payload)
    db.add(n)
    await push_service.push_to_user(db, recipient_id, type, payload)
    return n
