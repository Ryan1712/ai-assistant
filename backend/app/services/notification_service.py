import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification, User


async def list_notifications(db: AsyncSession, actor: User,
                             unread_only: bool = False) -> list[Notification]:
    query = select(Notification).where(Notification.recipient_id == actor.id,
                                       Notification.workspace_id == actor.workspace_id)
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    rows = await db.execute(query.order_by(Notification.created_at.desc()))
    return list(rows.scalars())


async def mark_read(db: AsyncSession, actor: User, notification_id: uuid.UUID) -> None:
    n = await db.get(Notification, notification_id)
    if n is None or n.recipient_id != actor.id or n.workspace_id != actor.workspace_id:
        raise HTTPException(404, "notification_not_found")
    if n.read_at is None:
        n.read_at = datetime.now(timezone.utc)
        await db.commit()


async def mark_all_read(db: AsyncSession, actor: User) -> None:
    await db.execute(
        update(Notification)
        .where(Notification.recipient_id == actor.id,
              Notification.workspace_id == actor.workspace_id,
              Notification.read_at.is_(None))
        .values(read_at=datetime.now(timezone.utc))
    )
    await db.commit()
