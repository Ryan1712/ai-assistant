import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, Role, Task, TaskAssignee, User


def require_ceo(actor: User) -> None:
    if actor.role != Role.ceo:
        raise HTTPException(403, "forbidden")


def require_root_ceo(actor: User) -> None:
    if not actor.is_root:
        raise HTTPException(403, "forbidden")


async def visible_user_ids(db: AsyncSession, actor: User) -> list[uuid.UUID]:
    if actor.role == Role.ceo:
        rows = await db.execute(
            select(User.id).where(User.workspace_id == actor.workspace_id)
        )
        return list(rows.scalars())
    if actor.role == Role.manager:
        rows = await db.execute(
            select(User.id).where(
                User.workspace_id == actor.workspace_id,
                User.manager_id == actor.id,
            )
        )
        return [actor.id, *rows.scalars()]
    return [actor.id]


async def direct_report_ids(db: AsyncSession, actor: User) -> list[uuid.UUID]:
    rows = await db.execute(select(User.id).where(
        User.workspace_id == actor.workspace_id, User.manager_id == actor.id,
    ))
    return list(rows.scalars())


async def can_assign_directive(db: AsyncSession, actor: User, recipient_id: uuid.UUID) -> bool:
    """Quyền tạo Directive (Phase 3 §7.1) — TÁCH BIỆT khỏi work_service's require_ceo (đó
    là quyết định thiết kế cố ý: work_service không có ma trận CEO/manager nào, Directive
    có logic riêng, không mở rộng phạm vi quyền của assign_task/create_task/update_task)."""
    if actor.role == Role.ceo:
        return True
    if actor.role == Role.manager:
        return recipient_id in await direct_report_ids(db, actor)
    return False


async def _assigned_task_ids(db: AsyncSession, actor: User, user_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    rows = await db.execute(select(TaskAssignee.task_id).where(
        TaskAssignee.workspace_id == actor.workspace_id,
        TaskAssignee.user_id.in_(user_ids),
    ))
    return set(rows.scalars())


async def visible_task_ids(db: AsyncSession, actor: User) -> set[uuid.UUID]:
    if actor.role == Role.ceo:
        rows = await db.execute(select(Task.id).where(Task.workspace_id == actor.workspace_id))
        return set(rows.scalars())
    uids = [actor.id]
    if actor.role == Role.manager:
        uids += await direct_report_ids(db, actor)
    ids = await _assigned_task_ids(db, actor, uids)
    if actor.role == Role.manager:
        owned = await db.execute(
            select(Task.id).join(Project, Task.project_id == Project.id).where(
                Task.workspace_id == actor.workspace_id, Project.owner_id == actor.id,
            )
        )
        ids |= set(owned.scalars())
    return ids


async def visible_project_ids(db: AsyncSession, actor: User) -> set[uuid.UUID]:
    if actor.role == Role.ceo:
        rows = await db.execute(select(Project.id).where(Project.workspace_id == actor.workspace_id))
        return set(rows.scalars())
    task_ids = await visible_task_ids(db, actor)
    ids: set[uuid.UUID] = set()
    if task_ids:
        rows = await db.execute(select(Task.project_id).where(Task.id.in_(task_ids)))
        ids = set(rows.scalars())
    if actor.role == Role.manager:
        rows = await db.execute(select(Project.id).where(
            Project.workspace_id == actor.workspace_id, Project.owner_id == actor.id,
        ))
        ids |= set(rows.scalars())
    return ids


async def can_update_progress(db: AsyncSession, actor: User, task: Task) -> bool:
    if task.workspace_id != actor.workspace_id:
        return False
    if actor.role == Role.ceo:
        return True
    uids = [actor.id]
    if actor.role == Role.manager:
        uids += await direct_report_ids(db, actor)
    assigned = await db.execute(select(TaskAssignee.id).where(
        TaskAssignee.task_id == task.id, TaskAssignee.user_id.in_(uids),
    ))
    return assigned.first() is not None


async def get_visible_task_or_404(db: AsyncSession, actor: User, task_id: uuid.UUID) -> Task:
    task = await db.get(Task, task_id)
    if task is None or task.workspace_id != actor.workspace_id:
        raise HTTPException(404, "task_not_found")
    if actor.role != Role.ceo and task.id not in await visible_task_ids(db, actor):
        raise HTTPException(404, "task_not_found")
    return task
