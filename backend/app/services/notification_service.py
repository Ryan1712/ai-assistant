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


async def get_preferences(actor: User) -> dict:
    return dict(actor.notification_prefs or {})


async def set_preference(db: AsyncSession, actor: User, type_: str, enabled: bool) -> dict:
    # Reassign (không mutate in-place) để SQLAlchemy nhận diện thay đổi trên cột JSON.
    actor.notification_prefs = {**(actor.notification_prefs or {}), type_: enabled}
    await db.commit()
    return dict(actor.notification_prefs)


async def is_type_enabled(db: AsyncSession, recipient_id: uuid.UUID, type_: str) -> bool:
    recipient = await db.get(User, recipient_id)
    if recipient is None:
        return True
    return (recipient.notification_prefs or {}).get(type_, True)
