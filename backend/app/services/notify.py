"""Helper tập trung: ghi Notification (in-app) + bắn push best-effort.
Mọi chỗ tạo thông báo dùng hàm này thay vì db.add(Notification(...)) trực tiếp."""
import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification
from app.services import notification_service, push_service


async def notify(db: AsyncSession, *, workspace_id: uuid.UUID, recipient_id: uuid.UUID,
                 type: str, payload: dict, created_at: datetime | None = None) -> Notification | None:
    # Người nhận tự tắt loại thông báo này (funtional-plan 6.6) → bỏ qua cả in-app lẫn
    # push, không tạo bản ghi để Notification Center không hiện loại đã tắt.
    if not await notification_service.is_type_enabled(db, recipient_id, type):
        return None
    kwargs = {"created_at": created_at} if created_at is not None else {}
    # created_at: override cho cron dùng now= giả lập (freeze-time test) — vd
    # watcher_service.send_morning_briefs dedup theo ngày dựa trên created_at,
    # để trống thì dùng default _now() (thời điểm ghi thật) như trước giờ.
    n = Notification(workspace_id=workspace_id, recipient_id=recipient_id,
                     type=type, payload=payload, **kwargs)
    db.add(n)
    await push_service.push_to_user(db, recipient_id, type, payload)
    return n
