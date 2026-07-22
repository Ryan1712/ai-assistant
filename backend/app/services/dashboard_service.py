"""Dashboard "Hôm nay" — tổng hợp đọc-only theo phạm vi quyền sẵn có.

Phạm vi task = visible_task_ids (employee: task mình; manager: mình + đội +
project mình own; CEO: cả workspace). Note luôn chỉ của chính actor.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import plans
from app.models import Note, Task, TaskAssignee, TaskStatus, TaskUpdate, User, Workspace
from app.permissions import visible_task_ids


def _task_out(t: Task) -> dict:
    return {"id": str(t.id), "title": t.title, "status": t.status.value,
            "percent": t.percent, "priority": t.priority.value,
            "deadline": t.deadline.isoformat() if t.deadline else None}


_VN_OFFSET = timedelta(hours=7)


async def today_dashboard(db: AsyncSession, actor: User, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    # Thi truong chinh la VN (UTC+7) — "hom nay" phai theo ngay lich VN, khong
    # phai UTC, keo task/note luc 00:00-06:59 sang gio VN bi tinh nham sang
    # ngay hom truoc (cung lop bug da fix o voice_service/audit_service).
    today = (now + _VN_OFFSET).date()
    task_ids = await visible_task_ids(db, actor)

    tasks: list[Task] = []
    if task_ids:
        rows = await db.execute(select(Task).where(Task.id.in_(task_ids)))
        tasks = list(rows.scalars())

    def _dl_date(t: Task):
        if t.deadline is None:
            return None
        dl = t.deadline if t.deadline.tzinfo else t.deadline.replace(tzinfo=timezone.utc)
        return (dl.astimezone(timezone.utc) + _VN_OFFSET).date()

    open_tasks = [t for t in tasks if t.status != TaskStatus.done]
    due_today = [t for t in open_tasks if _dl_date(t) == today]
    overdue = [t for t in open_tasks if (d := _dl_date(t)) is not None and d < today]
    in_progress = [t for t in open_tasks
                   if t.status == TaskStatus.in_progress and t not in due_today
                   and t not in overdue]

    recent_updates: list[dict] = []
    if task_ids:
        since = now - timedelta(hours=24)
        rows = await db.execute(
            select(TaskUpdate, Task.title, User.full_name)
            .join(Task, TaskUpdate.task_id == Task.id)
            .join(User, TaskUpdate.author_id == User.id)
            .where(TaskUpdate.task_id.in_(task_ids), TaskUpdate.created_at >= since)
            .order_by(TaskUpdate.created_at.desc())
        )
        recent_updates = [
            {"task_id": str(u.task_id), "task_title": title, "author": author,
             "content": u.content, "percent": u.percent,
             "created_at": u.created_at.isoformat()}
            for u, title, author in rows.all()
        ]

    notes_rows = await db.execute(select(Note).where(
        Note.workspace_id == actor.workspace_id, Note.author_id == actor.id,
        Note.note_date == today,
    ).order_by(Note.created_at.desc()))
    notes_today = [{"id": str(n.id), "content": n.content, "tags": n.tags or []}
                   for n in notes_rows.scalars()]

    my_open = await db.execute(
        select(TaskAssignee.task_id).join(Task, TaskAssignee.task_id == Task.id).where(
            TaskAssignee.user_id == actor.id, Task.status != TaskStatus.done,
        )
    )
    waiting_on_me = len(list(my_open.scalars()))

    # Dashboard đầy đủ (in_progress + cập nhật đội) chỉ gói Advanced (funtional-plan
    # 6.10); due_today/overdue/counters/notes là tiện ích cá nhân, luôn đầy đủ.
    ws = await db.get(Workspace, actor.workspace_id)
    full = plans.plan_allows(ws, "full_dashboard")

    # Tổng nhân viên của workspace (mọi thành viên).
    employee_count = (await db.execute(
        select(func.count()).select_from(User).where(User.workspace_id == actor.workspace_id)
    )).scalar_one()

    # Ghi chú mới nhất của actor (bất kỳ ngày nào) — khác notes_today (chỉ hôm nay).
    latest_note_row = (await db.execute(
        select(Note).where(
            Note.workspace_id == actor.workspace_id, Note.author_id == actor.id,
        ).order_by(Note.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    latest_note = (
        {"id": str(latest_note_row.id), "content": latest_note_row.content,
         "tags": latest_note_row.tags or [], "created_at": latest_note_row.created_at.isoformat()}
        if latest_note_row else None
    )

    return {
        "employee_count": employee_count,
        "latest_note": latest_note,
        "due_today": [_task_out(t) for t in due_today],
        "overdue": [_task_out(t) for t in overdue],
        "in_progress": [_task_out(t) for t in in_progress] if full else [],
        "recent_updates": recent_updates if full else [],
        "notes_today": notes_today,
        "counters": {"overdue": len(overdue), "waiting_on_me": waiting_on_me,
                     "updates_24h": len(recent_updates)},
    }
