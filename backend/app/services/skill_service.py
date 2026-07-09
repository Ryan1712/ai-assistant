import uuid

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Skill, SkillGrant, SkillVersion, Task, User
from app.permissions import require_ceo


async def _latest_version_num(db: AsyncSession, skill_id: uuid.UUID) -> int:
    row = await db.execute(select(func.max(SkillVersion.version))
                           .where(SkillVersion.skill_id == skill_id))
    return row.scalar() or 0


async def _get_skill_or_404(db: AsyncSession, actor: User, skill_id: uuid.UUID) -> Skill:
    skill = await db.get(Skill, skill_id)
    if skill is None or skill.workspace_id != actor.workspace_id:
        raise HTTPException(404, "skill_not_found")
    return skill


async def _skill_out(db: AsyncSession, skill: Skill) -> dict:
    return {"id": skill.id, "name": skill.name, "kind": skill.kind,
            "task_id": skill.task_id,
            "latest_version": await _latest_version_num(db, skill.id)}


async def create_skill(db: AsyncSession, actor: User, *, name: str, kind,
                       task_id=None, content: str) -> dict:
    require_ceo(actor)
    if task_id is not None:
        task = await db.get(Task, task_id)
        if task is None or task.workspace_id != actor.workspace_id:
            raise HTTPException(404, "task_not_found")
    skill = Skill(workspace_id=actor.workspace_id, name=name, kind=kind,
                  task_id=task_id, created_by=actor.id)
    db.add(skill)
    await db.flush()
    db.add(SkillVersion(workspace_id=actor.workspace_id, skill_id=skill.id,
                        version=1, content=content, created_by=actor.id))
    await db.commit()
    return await _skill_out(db, skill)


async def add_version(db: AsyncSession, actor: User, skill_id: uuid.UUID,
                      content: str) -> int:
    require_ceo(actor)
    skill = await _get_skill_or_404(db, actor, skill_id)
    version = await _latest_version_num(db, skill.id) + 1
    db.add(SkillVersion(workspace_id=actor.workspace_id, skill_id=skill.id,
                        version=version, content=content, created_by=actor.id))
    await db.commit()
    return version


async def grant_skill(db: AsyncSession, actor: User, skill_id: uuid.UUID,
                      user_id: uuid.UUID) -> bool:
    require_ceo(actor)
    skill = await _get_skill_or_404(db, actor, skill_id)
    target = await db.get(User, user_id)
    if target is None or target.workspace_id != actor.workspace_id:
        raise HTTPException(422, "invalid_grantee")
    existing = await db.execute(select(SkillGrant.id).where(
        SkillGrant.skill_id == skill.id, SkillGrant.user_id == user_id))
    if existing.first() is not None:
        return False
    db.add(SkillGrant(workspace_id=actor.workspace_id, skill_id=skill.id,
                      user_id=user_id, granted_by=actor.id))
    await db.commit()
    return True


async def list_skills(db: AsyncSession, actor: User) -> list[dict]:
    from app.models import Role
    if actor.role == Role.ceo:
        rows = await db.execute(select(Skill).where(Skill.workspace_id == actor.workspace_id))
    else:
        rows = await db.execute(
            select(Skill).join(SkillGrant, SkillGrant.skill_id == Skill.id).where(
                Skill.workspace_id == actor.workspace_id, SkillGrant.user_id == actor.id))
    return [await _skill_out(db, s) for s in rows.scalars()]
