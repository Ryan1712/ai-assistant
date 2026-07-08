import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Role, User


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
