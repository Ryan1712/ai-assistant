"""Watcher — morning brief (spec AI upgrade §10.2).

07:00 giờ VN mỗi ngày: gộp dashboard "Hôm nay" + tình trạng directive của
CEO, 1 lượt model_fast viết tóm tắt ngắn, notify() (in-app + push best-effort
qua notify() có sẵn). Cron gọi hàm này MỖI PHÚT (giống check_report_schedules/
check_task_deadlines) — guard giờ + dedup theo ngày nằm TRONG hàm, không dựa
vào độ chính xác của lịch cron. Dedup qua Notification đã có sẵn
(type="morning_brief", created_at trong ngày VN hôm nay) — cố ý KHÔNG thêm
cột/bảng mới cho việc này.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm_client import LLMClient, TextDelta
from app.models import Notification, Role, User, UserStatus
from app.services import dashboard_service, directive_service
from app.services.notify import notify
from app.tz import VN_TZ

logger = logging.getLogger(__name__)

_BRIEF_SYSTEM = (
    "Bạn viết bản tóm tắt buổi sáng cho CEO một công ty nhỏ, bằng tiếng Việt, "
    "tối đa 4-5 câu ngắn gọn. Dựa hoàn toàn vào số liệu được cho — không bịa thêm. "
    "Ưu tiên nhắc: việc quá hạn, việc đến hạn hôm nay, directive (việc đã giao) chưa "
    "được xác nhận. Nếu số liệu đều ổn (không có gì trễ/chưa xác nhận) thì viết 1-2 câu "
    "tích cực ngắn gọn, đừng liệt kê dài dòng những con số 0. Chỉ trả về đoạn tóm tắt, "
    "không thêm lời chào/lời dẫn/tiêu đề."
)


async def _summarize_brief(llm: LLMClient, dashboard: dict, directive_status: dict) -> str:
    pending = [d for d in directive_status.get("directives", [])
              if d["status"] in ("sent", "seen")]
    facts = (
        f"Task quá hạn: {len(dashboard['overdue'])}\n"
        f"Task đến hạn hôm nay: {len(dashboard['due_today'])}\n"
        f"Task đang làm: {len(dashboard['in_progress'])}\n"
        f"Cập nhật tiến độ 24h qua: {len(dashboard['recent_updates'])}\n"
        f"Directive (việc đã giao) chưa được xác nhận: {len(pending)}"
    )
    parts: list[str] = []
    async for event in llm.stream(
        system=_BRIEF_SYSTEM,
        messages=[{"role": "user", "content": [{"type": "text", "text": facts}]}],
        tools=[]):
        if isinstance(event, TextDelta):
            parts.append(event.text)
    return "".join(parts).strip()


async def send_morning_briefs(db: AsyncSession, llm: LLMClient, *,
                              now: datetime | None = None) -> int:
    """Trả số brief đã gửi thành công. 1 CEO lỗi (dashboard/directive/LLM) không
    được chặn CEO khác — bắt lỗi + rollback + log, tiếp tục vòng lặp (cùng
    pattern report_schedule_service.run_due_schedules)."""
    now = now or datetime.now(timezone.utc)
    now_vn = now.astimezone(VN_TZ)
    if not (now_vn.hour == 7 and now_vn.minute == 0):
        return 0

    day_start_vn = now_vn.replace(hour=0, minute=0, second=0, microsecond=0)
    day_start_utc = day_start_vn.astimezone(timezone.utc)

    # Chỉ lấy id trước, KHÔNG giữ object User qua vòng lặp — rollback() ở 1
    # lần lặp lỗi expire toàn bộ identity map, đọc thuộc tính object cũ sau đó
    # ném MissingGreenlet (cùng bài học report_schedule_service.run_due_schedules
    # / worker.py::process_conversation). db.get() lại mỗi vòng luôn an toàn.
    ceo_ids = [row for row in (await db.execute(select(User.id).where(
        User.role == Role.ceo, User.status == UserStatus.active
    ))).scalars()]

    count = 0
    for ceo_id in ceo_ids:
        try:
            ceo = await db.get(User, ceo_id)
            if ceo is None:
                continue
            already = (await db.execute(select(Notification.id).where(
                Notification.recipient_id == ceo.id, Notification.type == "morning_brief",
                Notification.created_at >= day_start_utc,
            ).limit(1))).scalar_one_or_none()
            if already is not None:
                continue

            dashboard = await dashboard_service.today_dashboard(db, ceo, now=now)
            directive_status = await directive_service.get_directive_status(db, ceo)
            summary = await _summarize_brief(llm, dashboard, directive_status)
            if not summary:
                continue  # LLM trả rỗng -> đừng gửi brief trống
            await notify(db, workspace_id=ceo.workspace_id, recipient_id=ceo.id,
                        type="morning_brief", payload={"summary": summary}, created_at=now)
            await db.commit()
            count += 1
        except Exception:
            logger.exception("morning brief fail cho CEO %s", ceo_id)
            await db.rollback()
    return count
