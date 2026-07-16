from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.services import audit_service

router = APIRouter(prefix="/api/v1", tags=["audit"])


@router.get("/audit-events")
async def list_audit_events(date_from: date | None = None, date_to: date | None = None,
                            actor: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    return await audit_service.list_audit_events(db, actor, date_from=date_from, date_to=date_to)
