import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import NotificationOut, UpdateNotificationPreferenceIn
from app.services import notification_service

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
async def list_notifications(unread_only: bool = False,
                             actor: User = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    return await notification_service.list_notifications(db, actor, unread_only=unread_only)


@router.get("/preferences", response_model=dict[str, bool])
async def get_preferences(actor: User = Depends(get_current_user)):
    return await notification_service.get_preferences(actor)


@router.patch("/preferences", response_model=dict[str, bool])
async def set_preference(body: UpdateNotificationPreferenceIn,
                         actor: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    return await notification_service.set_preference(db, actor, body.type, body.enabled)


@router.post("/{notification_id}/read", status_code=204)
async def mark_read(notification_id: uuid.UUID, actor: User = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)):
    await notification_service.mark_read(db, actor, notification_id)
    return Response(status_code=204)


@router.post("/read-all", status_code=204)
async def mark_all_read(actor: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    await notification_service.mark_all_read(db, actor)
    return Response(status_code=204)
