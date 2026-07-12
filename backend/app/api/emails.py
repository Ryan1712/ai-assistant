from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.services import email_service

router = APIRouter(prefix="/api/v1/emails", tags=["emails"])


@router.get("")
async def list_emails(box: Literal["inbox", "sent"] = "inbox",
                      actor: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    return await email_service.list_emails(db, actor, box=box)
