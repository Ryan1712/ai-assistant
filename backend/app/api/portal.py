from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.services import portal_service

router = APIRouter(prefix="/api/v1/portal", tags=["portal"])


@router.get("/reports")
async def list_portal_reports(actor: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    return await portal_service.list_reports(db, actor)


@router.get("/reports/{report_id}")
async def get_portal_report(report_id: str, actor: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    return await portal_service.get_report(db, actor, report_id)
