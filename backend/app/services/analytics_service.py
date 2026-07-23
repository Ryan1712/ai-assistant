"""Phân tích tổng hợp (Phase 6-style, feedback tester #1) — 2 tool đọc-only MỚI:
get_project_health (soi sâu 1 project) + get_progress_stats (so sánh kỳ này/kỳ trước).
Không xây get_workload_summary — dữ liệu đã có sẵn ở snapshot_service (mục "Nhân sự
& khối lượng"), xây thêm sẽ trùng lặp không ai dùng.
"""
import uuid
from datetime import datetime, time, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, Task, TaskStatus, TaskUpdate, User
from app.permissions import visible_project_ids, visible_task_ids
from app.tz import VN_TZ

_STALE_DAYS = 7
_PERIODS = {"week", "month"}


def _vn_date(dt: datetime | None):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)  # SQLite test trả naive — giá trị luôn UTC
    return dt.astimezone(VN_TZ).date()


async def get_project_health(db: AsyncSession, actor: User, project_id: uuid.UUID, *,
                             now: datetime | None = None) -> dict:
    """Đúng precedent snapshot_service (mục "Dự án"): 1 project vào visible_project_ids
    thì thấy TOÀN BỘ task của project đó, không lọc tiếp theo visible_task_ids — project
    đã là 1 lớp quyền riêng, không phải per-task."""
    now = now or datetime.now(timezone.utc)
    today_vn = _vn_date(now)

    project_ids = await visible_project_ids(db, actor)
    if project_id not in project_ids:
        raise HTTPException(404, "project_not_found")
    project = await db.get(Project, project_id)

    tasks = (await db.execute(
        select(Task).where(Task.project_id == project_id))).scalars().all()
    task_total = len(tasks)

    last_update_at: dict[uuid.UUID, datetime] = {}
    if tasks:
        rows = await db.execute(
            select(TaskUpdate.task_id, func.max(TaskUpdate.created_at))
            .where(TaskUpdate.task_id.in_([t.id for t in tasks]))
            .group_by(TaskUpdate.task_id)
        )
        last_update_at = dict(rows.all())

    blocked = []
    overdue = []
    stale = []
    for t in tasks:
        is_open = t.status != TaskStatus.done
        if t.status == TaskStatus.blocked:
            blocked.append({"task_id": str(t.id), "title": t.title,
                            "days_since_created": (today_vn - _vn_date(t.created_at)).days})
        dl_vn = _vn_date(t.deadline)
        if is_open and dl_vn is not None and dl_vn < today_vn:
            overdue.append({"task_id": str(t.id), "title": t.title,
                            "days_overdue": (today_vn - dl_vn).days})
        if is_open:
            last = last_update_at.get(t.id, t.created_at)
            last_vn = _vn_date(last)
            days_since_update = (today_vn - last_vn).days
            if days_since_update > _STALE_DAYS:
                stale.append({"task_id": str(t.id), "title": t.title,
                             "days_since_update": days_since_update})

    risk = "low"
    if overdue or (task_total and len(blocked) / task_total > 0.3):
        risk = "high"
    elif stale:
        risk = "medium"

    result = {
        "project_id": str(project_id), "project_name": project.name,
        "task_total": task_total,
        "percent_avg": round(sum(t.percent for t in tasks) / task_total) if tasks else 0,
        "blocked": blocked, "overdue": overdue, "stale": stale, "risk": risk,
    }
    if task_total == 0:
        result["note"] = "Project chưa có task nào."
    return result


def _period_bounds(now: datetime, period: str) -> dict:
    """Ranh giới kỳ hiện tại (từ đầu kỳ tới `now`) và kỳ trước (nguyên vẹn) — theo
    lịch giờ VN (tuần bắt đầu thứ 2, tháng theo lịch dương). Chưa có code nào trong
    repo làm date-bucketing kiểu này, viết mới hoàn toàn."""
    now_vn = now.astimezone(VN_TZ)
    if period == "week":
        today = now_vn.date()
        cur_start_date = today - timedelta(days=today.weekday())
        cur_start = datetime.combine(cur_start_date, time.min, tzinfo=VN_TZ)
        prev_start = cur_start - timedelta(days=7)
    else:
        cur_start = datetime(now_vn.year, now_vn.month, 1, tzinfo=VN_TZ)
        if now_vn.month == 1:
            prev_start = datetime(now_vn.year - 1, 12, 1, tzinfo=VN_TZ)
        else:
            prev_start = datetime(now_vn.year, now_vn.month - 1, 1, tzinfo=VN_TZ)
    return {"cur_start": cur_start, "cur_end": now, "prev_start": prev_start, "prev_end": cur_start}


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _empty_progress_stats(period: str) -> dict:
    return {
        "period": period,
        "current": {"completed": 0, "created": 0, "overdue": 0},
        "previous": {"completed": 0, "created": 0},
        "change": {"completed_diff": 0, "created_diff": 0},
        "note": "Không có task nào trong phạm vi bạn thấy.",
    }


async def get_progress_stats(db: AsyncSession, actor: User, *, period: str = "week",
                             project_id: uuid.UUID | None = None,
                             now: datetime | None = None) -> dict:
    if period not in _PERIODS:
        raise HTTPException(422, "invalid_period")
    now = now or datetime.now(timezone.utc)
    bounds = _period_bounds(now, period)

    if project_id is not None:
        project_ids = await visible_project_ids(db, actor)
        if project_id not in project_ids:
            raise HTTPException(404, "project_not_found")
        tasks = (await db.execute(
            select(Task).where(Task.project_id == project_id))).scalars().all()
    else:
        task_ids = await visible_task_ids(db, actor)
        tasks = []
        if task_ids:
            tasks = (await db.execute(
                select(Task).where(Task.id.in_(task_ids)))).scalars().all()

    if not tasks:
        return _empty_progress_stats(period)

    task_ids_set = {t.id for t in tasks}
    # cur_end = now: dùng "<=" vì 1 task tạo đúng thời điểm `now` vẫn phải tính vào kỳ
    # hiện tại (khác prev_end = mốc đầu kỳ, phải "<" để không đếm trùng vào cả 2 kỳ).
    created_cur = sum(1 for t in tasks
                      if bounds["cur_start"] <= _aware(t.created_at) <= bounds["cur_end"])
    created_prev = sum(1 for t in tasks
                       if bounds["prev_start"] <= _aware(t.created_at) < bounds["prev_end"])

    today_vn = _vn_date(now)
    overdue_now = sum(1 for t in tasks if t.status != TaskStatus.done
                      and (d := _vn_date(t.deadline)) is not None and d < today_vn)

    updates = (await db.execute(select(TaskUpdate).where(
        TaskUpdate.task_id.in_(task_ids_set), TaskUpdate.status == TaskStatus.done,
    ))).scalars().all()
    completed_cur = {u.task_id for u in updates
                     if bounds["cur_start"] <= _aware(u.created_at) <= bounds["cur_end"]}
    completed_prev = {u.task_id for u in updates
                      if bounds["prev_start"] <= _aware(u.created_at) < bounds["prev_end"]}

    return {
        "period": period,
        "current": {"completed": len(completed_cur), "created": created_cur,
                   "overdue": overdue_now},
        "previous": {"completed": len(completed_prev), "created": created_prev},
        "change": {"completed_diff": len(completed_cur) - len(completed_prev),
                  "created_diff": created_cur - created_prev},
    }
