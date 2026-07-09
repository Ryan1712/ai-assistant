import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification, Project, Task, TaskAssignee, TaskComment, TaskUpdate, User
from app.permissions import (
    can_update_progress,
    get_visible_task_or_404,
    require_ceo,
    visible_project_ids,
    visible_task_ids,
)


async def _validate_owner(db: AsyncSession, actor: User, owner_id) -> None:
    if owner_id is None:
        return
    owner = await db.get(User, owner_id)
    if owner is None or owner.workspace_id != actor.workspace_id:
        raise HTTPException(422, "invalid_owner")


async def create_project(db: AsyncSession, actor: User, *, name: str, goal: str = "",
                         deadline=None, owner_id=None) -> Project:
    require_ceo(actor)
    await _validate_owner(db, actor, owner_id)
    project = Project(workspace_id=actor.workspace_id, name=name, goal=goal,
                      deadline=deadline, owner_id=owner_id, created_by=actor.id)
    db.add(project)
    await db.commit()
    return project


async def update_project(db: AsyncSession, actor: User, project_id: uuid.UUID,
                         patch: dict) -> Project:
    require_ceo(actor)
    project = await db.get(Project, project_id)
    if project is None or project.workspace_id != actor.workspace_id:
        raise HTTPException(404, "project_not_found")
    if "owner_id" in patch:
        await _validate_owner(db, actor, patch["owner_id"])
    for key, value in patch.items():
        setattr(project, key, value)
    await db.commit()
    return project


async def list_projects(db: AsyncSession, actor: User) -> list[Project]:
    ids = await visible_project_ids(db, actor)
    if not ids:
        return []
    rows = await db.execute(select(Project).where(Project.id.in_(ids)))
    return list(rows.scalars())


async def _assignee_ids(db: AsyncSession, task_id: uuid.UUID) -> list[uuid.UUID]:
    rows = await db.execute(select(TaskAssignee.user_id).where(TaskAssignee.task_id == task_id))
    return list(rows.scalars())


async def _task_out(db: AsyncSession, task: Task) -> dict:
    return {
        "id": task.id, "project_id": task.project_id, "title": task.title,
        "description": task.description, "status": task.status, "percent": task.percent,
        "deadline": task.deadline, "priority": task.priority,
        "assignee_ids": await _assignee_ids(db, task.id),
    }


async def create_task(db: AsyncSession, actor: User, *, project_id: uuid.UUID,
                      title: str, description: str = "", deadline=None,
                      priority=None) -> dict:
    require_ceo(actor)
    project = await db.get(Project, project_id)
    if project is None or project.workspace_id != actor.workspace_id:
        raise HTTPException(404, "project_not_found")
    task = Task(workspace_id=actor.workspace_id, project_id=project_id, title=title,
                description=description, deadline=deadline, created_by=actor.id,
                **({"priority": priority} if priority else {}))
    db.add(task)
    await db.commit()
    return await _task_out(db, task)


async def update_task(db: AsyncSession, actor: User, task_id: uuid.UUID, patch: dict) -> dict:
    require_ceo(actor)
    task = await db.get(Task, task_id)
    if task is None or task.workspace_id != actor.workspace_id:
        raise HTTPException(404, "task_not_found")
    for key, value in patch.items():
        setattr(task, key, value)
    await db.commit()
    return await _task_out(db, task)


async def assign_task(db: AsyncSession, actor: User, task_id: uuid.UUID,
                      user_id: uuid.UUID) -> bool:
    """Trả về True nếu tạo assignment mới, False nếu đã tồn tại (idempotent)."""
    require_ceo(actor)
    task = await db.get(Task, task_id)
    if task is None or task.workspace_id != actor.workspace_id:
        raise HTTPException(404, "task_not_found")
    target = await db.get(User, user_id)
    if target is None or target.workspace_id != actor.workspace_id:
        raise HTTPException(422, "invalid_assignee")
    existing = await db.execute(select(TaskAssignee.id).where(
        TaskAssignee.task_id == task_id, TaskAssignee.user_id == user_id))
    if existing.first() is not None:
        return False
    db.add(TaskAssignee(workspace_id=actor.workspace_id, task_id=task_id, user_id=user_id))
    db.add(Notification(workspace_id=actor.workspace_id, recipient_id=user_id,
                        type="task_assigned",
                        payload={"task_id": str(task_id), "title": task.title}))
    await db.commit()
    return True


async def unassign_task(db: AsyncSession, actor: User, task_id: uuid.UUID,
                        user_id: uuid.UUID) -> None:
    require_ceo(actor)
    task = await db.get(Task, task_id)
    if task is None or task.workspace_id != actor.workspace_id:
        raise HTTPException(404, "task_not_found")
    row = (await db.execute(select(TaskAssignee).where(
        TaskAssignee.task_id == task_id, TaskAssignee.user_id == user_id,
    ))).scalar_one_or_none()
    if row:
        await db.delete(row)
        await db.commit()


async def list_tasks(db: AsyncSession, actor: User) -> list[dict]:
    ids = await visible_task_ids(db, actor)
    if not ids:
        return []
    rows = await db.execute(select(Task).where(Task.id.in_(ids)))
    return [await _task_out(db, t) for t in rows.scalars()]


async def get_task(db: AsyncSession, actor: User, task_id: uuid.UUID) -> dict:
    task = await get_visible_task_or_404(db, actor, task_id)
    return await _task_out(db, task)


async def _notify_task_update(db: AsyncSession, actor: User, task: Task) -> None:
    recipients: set[uuid.UUID] = set(await _assignee_ids(db, task.id))
    if actor.manager_id:
        recipients.add(actor.manager_id)
    root = (await db.execute(select(User.id).where(
        User.workspace_id == actor.workspace_id, User.is_root,
    ))).scalar_one_or_none()
    if root:
        recipients.add(root)
    recipients.discard(actor.id)
    for rid in recipients:
        db.add(Notification(workspace_id=actor.workspace_id, recipient_id=rid,
                            type="task_update",
                            payload={"task_id": str(task.id), "author_id": str(actor.id)}))


async def add_task_update(db: AsyncSession, actor: User, task_id: uuid.UUID, *,
                          content: str = "", percent=None, status=None) -> TaskUpdate:
    task = await get_visible_task_or_404(db, actor, task_id)
    if not await can_update_progress(db, actor, task):
        raise HTTPException(403, "forbidden")
    upd = TaskUpdate(workspace_id=actor.workspace_id, task_id=task.id, author_id=actor.id,
                     content=content, percent=percent, status=status)
    db.add(upd)
    if percent is not None:
        task.percent = percent
    if status is not None:
        task.status = status
    await _notify_task_update(db, actor, task)
    await db.commit()
    return upd


async def list_task_updates(db: AsyncSession, actor: User, task_id: uuid.UUID) -> list[TaskUpdate]:
    task = await get_visible_task_or_404(db, actor, task_id)
    rows = await db.execute(select(TaskUpdate).where(TaskUpdate.task_id == task.id)
                            .order_by(TaskUpdate.created_at.desc(), TaskUpdate.id.desc()))
    return list(rows.scalars())


async def add_comment(db: AsyncSession, actor: User, task_id: uuid.UUID,
                      content: str) -> TaskComment:
    task = await get_visible_task_or_404(db, actor, task_id)
    comment = TaskComment(workspace_id=actor.workspace_id, task_id=task.id,
                          author_id=actor.id, content=content)
    db.add(comment)
    await db.commit()
    return comment


async def list_comments(db: AsyncSession, actor: User, task_id: uuid.UUID) -> list[TaskComment]:
    task = await get_visible_task_or_404(db, actor, task_id)
    rows = await db.execute(select(TaskComment).where(TaskComment.task_id == task.id)
                            .order_by(TaskComment.created_at.asc(), TaskComment.id.asc()))
    return list(rows.scalars())
