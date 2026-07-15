import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import permissions
from app.db import get_db
from app.deps import get_current_user
from app.models import Device, User
from app.schemas import DeviceOut, OffboardIn, UserOut
from app.services import auth_service

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


@router.post("/{user_id}/lock", status_code=204)
async def lock_user(
    user_id: uuid.UUID,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await auth_service.lock_user(db, actor, user_id)
    return Response(status_code=204)


@router.post("/{user_id}/unlock", status_code=204)
async def unlock_user(
    user_id: uuid.UUID,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await auth_service.unlock_user(db, actor, user_id)
    return Response(status_code=204)


@router.post("/{user_id}/offboard")
async def offboard_user(
    user_id: uuid.UUID,
    body: OffboardIn = OffboardIn(),
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await auth_service.offboard_user(db, actor, user_id, body.successor_id)
