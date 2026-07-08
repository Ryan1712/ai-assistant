from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import InviteCreateIn, InviteOut
from app.services import auth_service

router = APIRouter(prefix="/api/v1/invites", tags=["invites"])


@router.post("", response_model=InviteOut, status_code=201)
async def create_invite(
    body: InviteCreateIn,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    invite = await auth_service.create_invite(
        db, actor=actor, role=body.role, manager_id=body.manager_id,
    )
    return invite
