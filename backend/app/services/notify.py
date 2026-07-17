"""Helper tập trung: ghi Notification (in-app) + bắn push best-effort.
Mọi chỗ tạo thông báo dùng hàm này thay vì db.add(Notification(...)) trực tiếp."""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification
from app.services import notification_service, push_service


async def notify(db: AsyncSession, *, workspace_id: uuid.UUID, recipient_id: uuid.UUID,
                 type: str, payload: dict) -> Notification | None:
    # Người nhận tự tắt loại thông báo này (funtional-plan 6.6) → bỏ qua cả in-app lẫn
    # push, không tạo bản ghi để Notification Center không hiện loại đã tắt.
    if not await notification_service.is_type_enabled(db, recipient_id, type):
        return None
    n = Notification(workspace_id=workspace_id, recipient_id=recipient_id,
                     type=type, payload=payload)
    db.add(n)
    await push_service.push_to_user(db, recipient_id, type, payload)
    return n
