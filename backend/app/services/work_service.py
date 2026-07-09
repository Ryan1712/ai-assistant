import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, User
from app.permissions import require_ceo, visible_project_ids


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
