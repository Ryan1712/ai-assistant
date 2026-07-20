"""Workspace snapshot (spec AI upgrade §5) — bức tranh công ty dạng text nén.

Kiến trúc: build DATA per-workspace (SQL aggregates, KHÔNG LLM) cache Redis TTL;
render TEXT per-actor tại request bằng visible_* của app/permissions.py (quyền
luôn tươi — data cache chung, không lộ vượt quyền). Lỗi bất kỳ → trả "" (snapshot
là tăng cường, không bao giờ được phá chat).

Refresh (deviation §5.2 đã chốt): lazy build-on-miss + TTL + invalidate() gọi từ
agent loop sau write-tool — thay cho worker nền/debounce arq (spec cho phép chọn
cách rẻ hơn).
"""
from __future__ import annotations

import abc
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, Task, TaskAssignee, TaskStatus, TaskUpdate, User
from app.tz import VN_TZ

logger = logging.getLogger(__name__)


class SnapshotStore(abc.ABC):
    @abc.abstractmethod
    async def get(self, key: str) -> str | None: ...

    @abc.abstractmethod
    async def set(self, key: str, value: str, ttl: int) -> None: ...

    @abc.abstractmethod
    async def delete(self, key: str) -> None: ...


class FakeSnapshotStore(SnapshotStore):
    """Test double: dict trong RAM, không TTL thật; .deleted ghi lại invalidation."""

    def __init__(self):
        self.data: dict[str, str] = {}
        self.deleted: list[str] = []

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def set(self, key: str, value: str, ttl: int) -> None:
        self.data[key] = value

    async def delete(self, key: str) -> None:
        self.data.pop(key, None)
        self.deleted.append(key)


class RedisSnapshotStore(SnapshotStore):
    def __init__(self, redis):
        self._redis = redis

    async def get(self, key: str) -> str | None:
        raw = await self._redis.get(key)
        if raw is None:
            return None
        return raw.decode() if isinstance(raw, bytes) else raw

    async def set(self, key: str, value: str, ttl: int) -> None:
        await self._redis.set(key, value, ex=ttl)

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)


@lru_cache
def get_snapshot_store() -> SnapshotStore:
    import redis.asyncio as redis_asyncio

    from app.config import get_settings

    # Timeout ngắn: redis chết thì get_snapshot_text bắt exception trả "" —
    # không được treo request chat vài chục giây chờ TCP.
    client = redis_asyncio.from_url(get_settings().redis_url,
                                    socket_connect_timeout=2, socket_timeout=2)
    return RedisSnapshotStore(client)


def _key(workspace_id: uuid.UUID | str) -> str:
    return f"snapshot:{workspace_id}"


_DOING_LIMIT = 3


def _vn_date(dt: datetime | None):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)  # SQLite test trả naive — giá trị luôn UTC
    return dt.astimezone(VN_TZ).date()


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


async def build_workspace_data(db: AsyncSession, workspace_id, *,
                               now: datetime | None = None) -> dict:
    """Aggregates SQL per-workspace, KHÔNG LLM, KHÔNG quyền (cắt quyền ở render).
    Mọi id là str để json round-trip qua Redis không đổi kiểu."""
    now = now or datetime.now(timezone.utc)
    today_vn = _vn_date(now)

    projects = (await db.execute(select(Project).where(
        Project.workspace_id == workspace_id).order_by(Project.created_at.asc())
    )).scalars().all()
    users = (await db.execute(select(User).where(
        User.workspace_id == workspace_id).order_by(User.full_name.asc())
    )).scalars().all()
    tasks = (await db.execute(select(Task).where(
        Task.workspace_id == workspace_id))).scalars().all()
    assignees = (await db.execute(select(TaskAssignee).where(
        TaskAssignee.workspace_id == workspace_id))).scalars().all()

    name_by_uid = {u.id: u.full_name for u in users}
    pname_by_id = {p.id: p.name for p in projects}
    task_by_id = {t.id: t for t in tasks}
    uids_by_task: dict = {}
    tids_by_user: dict = {}
    for a in assignees:
        uids_by_task.setdefault(a.task_id, []).append(a.user_id)
        tids_by_user.setdefault(a.user_id, []).append(a.task_id)

    def _is_open(t: Task) -> bool:
        return t.status != TaskStatus.done

    def _is_overdue(t: Task) -> bool:
        d = _vn_date(t.deadline)
        return _is_open(t) and d is not None and d < today_vn

    out_projects = []
    for p in projects:
        pt = [t for t in tasks if t.project_id == p.id]
        out_projects.append({
            "id": str(p.id), "name": p.name, "status": p.status,
            "deadline": _iso(p.deadline),
            "task_total": len(pt),
            "task_open": sum(1 for t in pt if _is_open(t)),
            "task_blocked": sum(1 for t in pt if t.status == TaskStatus.blocked),
            "task_overdue": sum(1 for t in pt if _is_overdue(t)),
            "task_done": sum(1 for t in pt if t.status == TaskStatus.done),
            "percent_avg": round(sum(t.percent for t in pt) / len(pt)) if pt else 0,
        })

    since = now - timedelta(hours=24)
    upd_rows = (await db.execute(
        select(TaskUpdate).where(TaskUpdate.workspace_id == workspace_id,
                                 TaskUpdate.created_at >= since)
        .order_by(TaskUpdate.created_at.desc()))).scalars().all()
    last_update_by_author: dict = {}
    all_upd_rows = (await db.execute(
        select(TaskUpdate.author_id, TaskUpdate.created_at).where(
            TaskUpdate.workspace_id == workspace_id))).all()
    for author_id, created_at in all_upd_rows:
        cur = last_update_by_author.get(author_id)
        if cur is None or created_at > cur:
            last_update_by_author[author_id] = created_at

    out_users = []
    for u in users:
        utasks = [task_by_id[tid] for tid in tids_by_user.get(u.id, [])
                  if tid in task_by_id]
        open_tasks = [t for t in utasks if _is_open(t)]
        doing = sorted((t for t in open_tasks if t.status == TaskStatus.in_progress),
                       key=lambda t: (t.deadline is None,
                                      t.deadline or datetime.max.replace(tzinfo=timezone.utc)))
        out_users.append({
            "id": str(u.id), "full_name": u.full_name, "role": u.role.value,
            "manager_name": name_by_uid.get(u.manager_id),
            "open_count": len(open_tasks),
            "overdue_count": sum(1 for t in open_tasks if _is_overdue(t)),
            "last_update_at": _iso(last_update_by_author.get(u.id)),
            "doing": [{"task_id": str(t.id), "title": t.title,
                       "project_name": pname_by_id.get(t.project_id, ""),
                       "percent": t.percent, "deadline": _iso(t.deadline)}
                      for t in doing[:_DOING_LIMIT]],
        })

    def _task_line(t: Task) -> dict:
        return {"task_id": str(t.id), "title": t.title,
                "project_name": pname_by_id.get(t.project_id, ""),
                "assignees": [name_by_uid.get(uid, "?")
                              for uid in uids_by_task.get(t.id, [])]}

    due_today = [t for t in tasks if _is_open(t) and _vn_date(t.deadline) == today_vn]
    overdue = [t for t in tasks if _is_overdue(t)]

    return {
        "built_at": now.isoformat(),
        "projects": out_projects,
        "users": out_users,
        "due_today": [_task_line(t) for t in due_today],
        "overdue": [{**_task_line(t), "deadline": _iso(t.deadline)} for t in overdue],
        "updates_24h": [{"task_id": str(r.task_id),
                         "task_title": task_by_id[r.task_id].title
                         if r.task_id in task_by_id else "?",
                         "author": name_by_uid.get(r.author_id, "?"),
                         "content": r.content, "percent": r.percent,
                         "at": _iso(r.created_at)} for r in upd_rows],
    }
