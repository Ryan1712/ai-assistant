from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.services import auth_service

router = APIRouter(prefix="/api/v1/workspace", tags=["workspace"])


@router.get("/invite-code")
async def get_invite_code(actor: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    return {"invite_code": await auth_service.get_invite_code(db, actor)}


@router.post("/invite-code/rotate")
async def rotate_invite_code(actor: User = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    return {"invite_code": await auth_service.rotate_invite_code(db, actor)}
