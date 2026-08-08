"""Helper tập trung: ghi Notification (in-app) + bắn push best-effort.
Mọi chỗ tạo thông báo dùng hàm này thay vì db.add(Notification(...)) trực tiếp."""
import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification
from app.services import notification_service, push_service


async def notify(db: AsyncSession, *, workspace_id: uuid.UUID, recipient_id: uuid.UUID,
                 type: str, payload: dict, created_at: datetime | None = None) -> Notification | None:
    """CẢNH BÁO (finding #11, audit 2026-07-26, re-verify 2026-08-08, LOW): hàm này
    gọi push_service.push_to_user() TRƯỚC khi caller db.commit() — nếu transaction
    của caller sau đó rollback (lỗi ở bước nào đó phía sau lệnh notify()), push đã
    bắn ra ngoài rồi nhưng Notification in-app tương ứng lại KHÔNG được ghi (mất
    đồng bộ giữa push đã gửi và in-app không tồn tại). Best-effort nên rủi ro thấp
    trong thực tế (push tự nuốt lỗi, không throw), nhưng vẫn là smell.

    KHÔNG refactor tách push ra khỏi notify() ở đây: notify() được gọi từ RẤT NHIỀU
    call site khác nhau (auth_service, email_service, directive_service,
    report_schedule_service, watcher_service, work_service, agent/worker.py) theo
    những cách không nhất quán — nhiều nơi gọi giữa 1 vòng lặp trước 1 commit dùng
    chung ở cuối, một số nơi mỗi notify() đi kèm 1 commit riêng ngay sau. Đổi
    signature (tách phần push để caller tự gọi SAU commit) là thay đổi rủi ro cao,
    phải sửa đồng loạt nhiều luồng nghiệp vụ trong 1 lần — ưu tiên an toàn, để
    nguyên hành vi hiện tại. Nếu cần sửa thật, tách thành task riêng đi qua từng
    call site một cách có kiểm soát (test riêng cho từng luồng)."""
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
