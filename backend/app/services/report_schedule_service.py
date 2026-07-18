"""Báo cáo định kỳ tự động (funtional-plan 6.5 nâng cao, gói Advanced).

CEO đặt lịch qua chat ("mỗi sáng thứ 2 lúc 8h") → arq cron quét bảng
ReportSchedule mỗi phút (xem app/agent/worker.py::check_report_schedules),
gọi lại report_service.generate_report sẵn có rồi notify() người nhận.
"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import plans
from app.models import Project, ReportSchedule, TaskStatus, User, Workspace
from app.permissions import require_ceo
from app.services import report_service
from app.services.notify import notify
from app.tz import VN_TZ

logger = logging.getLogger(__name__)


def compute_next_run(after: datetime, weekday: int | None, hour: int, minute: int) -> datetime:
    """Lần chạy kế tiếp SAU `after` (không bao giờ trả về đúng `after`).

    weekday/hour/minute hiểu theo GIỜ VIỆT NAM (UTC+7) — CEO đặt '8h sáng thứ 2'
    là 8h VN chứ không phải 8h UTC (=15h VN). Trả về datetime UTC (DB lưu UTC).
    """
    if after.tzinfo is None:
        after = after.replace(tzinfo=timezone.utc)
    after_vn = after.astimezone(VN_TZ)
    candidate = after_vn.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= after_vn:
        candidate += timedelta(days=1)
    if weekday is not None:
        while candidate.weekday() != weekday:
            candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc)


async def create_schedule(db: AsyncSession, actor: User, *, weekday: int | None,
                          hour: int, minute: int = 0,
                          project_id=None, assignee_id=None, status: TaskStatus | None = None,
                          recipient_id=None) -> ReportSchedule:
    require_ceo(actor)
    ws = await db.get(Workspace, actor.workspace_id)
    if not plans.plan_allows(ws, "scheduled_reports"):
        raise HTTPException(403, "advanced_plan_required")
    if project_id is not None:
        project = await db.get(Project, project_id)
        if project is None or project.workspace_id != actor.workspace_id:
            raise HTTPException(404, "project_not_found")
    if assignee_id is not None:
        assignee = await db.get(User, assignee_id)
        if assignee is None or assignee.workspace_id != actor.workspace_id:
            raise HTTPException(404, "user_not_found")
    recipient = actor.id
    if recipient_id is not None:
        target = await db.get(User, recipient_id)
        if target is None or target.workspace_id != actor.workspace_id:
            raise HTTPException(404, "user_not_found")
        recipient = recipient_id
    now = datetime.now(timezone.utc)
    sched = ReportSchedule(
        workspace_id=actor.workspace_id, created_by=actor.id, recipient_id=recipient,
        weekday=weekday, hour=hour, minute=minute, project_id=project_id,
        assignee_id=assignee_id, status=status,
        next_run_at=compute_next_run(now, weekday, hour, minute))
    db.add(sched)
    await db.commit()
    return sched


async def list_schedules(db: AsyncSession, actor: User) -> list[ReportSchedule]:
    require_ceo(actor)
    rows = await db.execute(select(ReportSchedule).where(
        ReportSchedule.workspace_id == actor.workspace_id
    ).order_by(ReportSchedule.created_at.asc()))
    return list(rows.scalars())


async def delete_schedule(db: AsyncSession, actor: User, schedule_id) -> None:
    require_ceo(actor)
    sched = await db.get(ReportSchedule, schedule_id)
    if sched is None or sched.workspace_id != actor.workspace_id:
        raise HTTPException(404, "schedule_not_found")
    await db.delete(sched)
    await db.commit()


async def run_due_schedules(db: AsyncSession, *, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    due_ids = [s.id for s in (await db.execute(select(ReportSchedule).where(
        ReportSchedule.active.is_(True), ReportSchedule.next_run_at <= now
    ))).scalars()]
    results = []
    for sched_id in due_ids:
        sched = await db.get(ReportSchedule, sched_id)
        if sched is None:
            continue
        try:
            actor = await db.get(User, sched.created_by)
            if actor is not None:
                out = await report_service.generate_report(
                    db, actor, project_id=sched.project_id, assignee_id=sched.assignee_id,
                    status=sched.status)
                await notify(db, workspace_id=sched.workspace_id,
                            recipient_id=sched.recipient_id, type="scheduled_report",
                            payload={"report_id": out["report_id"], "summary": out["summary"],
                                     "schedule_id": str(sched.id)})
                results.append({"schedule_id": str(sched.id), "report_id": out["report_id"]})
        except Exception:
            # 1 lịch hỏng (creator mất quyền CEO, project bị xóa...) không được kéo
            # sập cả cron chạy-mỗi-phút; vẫn tiến next_run_at để không retry vô hạn.
            logger.exception("report schedule %s failed", sched_id)
            await db.rollback()
            sched = await db.get(ReportSchedule, sched_id)
            if sched is None:
                continue
        sched.last_run_at = now
        sched.next_run_at = compute_next_run(now, sched.weekday, sched.hour, sched.minute)
        await db.commit()
    return results
