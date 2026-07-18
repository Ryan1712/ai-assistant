import uuid

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Role, Skill, SkillGrant, SkillUsageLog, SkillVersion, Task, TaskAssignee, TaskUpdate, User
from app import plans
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
    await plans.enforce_limit(db, actor.workspace_id, "skills")
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


async def list_grants(db: AsyncSession, actor: User, skill_id: uuid.UUID) -> list[dict]:
    require_ceo(actor)
    skill = await _get_skill_or_404(db, actor, skill_id)
    rows = await db.execute(
        select(SkillGrant.user_id, User.full_name).join(User, User.id == SkillGrant.user_id)
        .where(SkillGrant.skill_id == skill.id).order_by(User.full_name.asc()))
    return [{"user_id": str(uid), "full_name": name} for uid, name in rows.all()]


async def revoke_grant(db: AsyncSession, actor: User, skill_id: uuid.UUID,
                       user_id: uuid.UUID) -> None:
    require_ceo(actor)
    skill = await _get_skill_or_404(db, actor, skill_id)
    grant = (await db.execute(select(SkillGrant).where(
        SkillGrant.skill_id == skill.id, SkillGrant.user_id == user_id))).scalar_one_or_none()
    if grant is None:
        raise HTTPException(404, "grant_not_found")
    await db.delete(grant)
    await db.commit()


async def list_skills(db: AsyncSession, actor: User) -> list[dict]:
    if actor.role == Role.ceo:
        rows = await db.execute(select(Skill).where(Skill.workspace_id == actor.workspace_id))
    else:
        rows = await db.execute(
            select(Skill).join(SkillGrant, SkillGrant.skill_id == Skill.id).where(
                Skill.workspace_id == actor.workspace_id, SkillGrant.user_id == actor.id))
    return [await _skill_out(db, s) for s in rows.scalars()]


async def _task_state(db: AsyncSession, task: Task) -> dict:
    assignee_rows = await db.execute(
        select(User.email).join(TaskAssignee, TaskAssignee.user_id == User.id)
        .where(TaskAssignee.task_id == task.id))
    updates = await db.execute(
        select(TaskUpdate).where(TaskUpdate.task_id == task.id)
        .order_by(TaskUpdate.created_at.desc(), TaskUpdate.id.desc()).limit(5))
    return {
        "id": str(task.id), "title": task.title, "status": task.status.value,
        "percent": task.percent,
        "deadline": task.deadline.isoformat() if task.deadline else None,
        "priority": task.priority.value,
        "assignees": list(assignee_rows.scalars()),
        "latest_updates": [
            {"author_id": str(u.author_id), "content": u.content, "percent": u.percent,
             "created_at": u.created_at.isoformat()}
            for u in updates.scalars()
        ],
    }


async def use_skill(db: AsyncSession, actor: User, skill_id: uuid.UUID) -> dict:
    skill = await _get_skill_or_404(db, actor, skill_id)
    if actor.role != Role.ceo:
        granted = await db.execute(select(SkillGrant.id).where(
            SkillGrant.skill_id == skill.id, SkillGrant.user_id == actor.id))
        if granted.first() is None:
            raise HTTPException(403, "skill_not_granted")
    latest = (await db.execute(
        select(SkillVersion).where(SkillVersion.skill_id == skill.id)
        .order_by(SkillVersion.version.desc()).limit(1))).scalar_one()
    task_state = None
    if skill.task_id is not None:
        task = await db.get(Task, skill.task_id)
        if task is not None:
            task_state = await _task_state(db, task)
    db.add(SkillUsageLog(workspace_id=actor.workspace_id, skill_id=skill.id,
                         version=latest.version, user_id=actor.id))
    await db.commit()
    return {"skill_id": str(skill.id), "name": skill.name, "kind": skill.kind.value,
            "version": latest.version, "content": latest.content,
            "task_state": task_state}
