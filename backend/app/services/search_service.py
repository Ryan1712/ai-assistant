from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Note, Role, Skill, SkillGrant, Task, User, VoiceNote
from app.permissions import visible_task_ids, visible_user_ids

_LIMIT = 20


async def _search_tasks(db: AsyncSession, actor: User, q: str) -> list[dict]:
    ids = await visible_task_ids(db, actor)
    if not ids:
        return []
    rows = await db.execute(
        select(Task).where(
            Task.id.in_(ids),
            or_(Task.title.ilike(f"%{q}%"), Task.description.ilike(f"%{q}%")),
        ).order_by(Task.created_at.desc()).limit(_LIMIT)
    )
    return [{"id": str(t.id), "title": t.title, "status": t.status.value,
            "project_id": str(t.project_id)} for t in rows.scalars()]


async def _search_notes(db: AsyncSession, actor: User, q: str) -> list[dict]:
    rows = await db.execute(
        select(Note).where(
            Note.workspace_id == actor.workspace_id, Note.author_id == actor.id,
            Note.content.ilike(f"%{q}%"),
        ).order_by(Note.created_at.desc()).limit(_LIMIT)
    )
    return [{"id": str(n.id), "content": n.content, "note_date": n.note_date.isoformat()}
           for n in rows.scalars()]


async def _search_voice_notes(db: AsyncSession, actor: User, q: str) -> list[dict]:
    rows = await db.execute(
        select(VoiceNote).where(
            VoiceNote.workspace_id == actor.workspace_id, VoiceNote.author_id == actor.id,
            VoiceNote.transcript.ilike(f"%{q}%"),
        ).order_by(VoiceNote.created_at.desc()).limit(_LIMIT)
    )
    return [{"id": str(v.id), "transcript": v.transcript,
            "created_at": v.created_at.isoformat()} for v in rows.scalars()]


async def _search_users(db: AsyncSession, actor: User, q: str) -> list[dict]:
    ids = await visible_user_ids(db, actor)
    if not ids:
        return []
    rows = await db.execute(
        select(User).where(
            User.id.in_(ids),
            or_(User.full_name.ilike(f"%{q}%"), User.email.ilike(f"%{q}%")),
        ).order_by(User.full_name.asc()).limit(_LIMIT)
    )
    return [{"id": str(u.id), "full_name": u.full_name, "email": u.email,
            "role": u.role.value} for u in rows.scalars()]


async def _search_skills(db: AsyncSession, actor: User, q: str) -> list[dict]:
    query = select(Skill).where(Skill.workspace_id == actor.workspace_id,
                                Skill.name.ilike(f"%{q}%"))
    if actor.role != Role.ceo:
        query = query.join(SkillGrant, SkillGrant.skill_id == Skill.id).where(
            SkillGrant.user_id == actor.id)
    rows = await db.execute(query.order_by(Skill.created_at.desc()).limit(_LIMIT))
    return [{"id": str(s.id), "name": s.name, "kind": s.kind.value} for s in rows.scalars()]


async def search(db: AsyncSession, actor: User, q: str) -> dict:
    return {
        "tasks": await _search_tasks(db, actor, q),
        "notes": await _search_notes(db, actor, q),
        "voice_notes": await _search_voice_notes(db, actor, q),
        "users": await _search_users(db, actor, q),
        "skills": await _search_skills(db, actor, q),
    }
