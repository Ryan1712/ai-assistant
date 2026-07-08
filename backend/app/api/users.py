import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import permissions
from app.db import get_db
from app.deps import get_current_user
from app.models import Device, User
from app.schemas import DeviceOut, UserOut

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user


@router.get("", response_model=list[UserOut])
async def list_users(
    actor: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    ids = await permissions.visible_user_ids(db, actor)
    rows = await db.execute(select(User).where(User.id.in_(ids)))
    return list(rows.scalars())


@router.get("/{user_id}/devices", response_model=list[DeviceOut])
async def list_devices(
    user_id: uuid.UUID,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    permissions.require_ceo(actor)
    rows = await db.execute(select(Device).where(
        Device.user_id == user_id, Device.workspace_id == actor.workspace_id,
    ))
    return list(rows.scalars())
