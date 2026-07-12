from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.services import dashboard_service

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/today")
async def today(actor: User = Depends(get_current_user),
                db: AsyncSession = Depends(get_db)):
    return await dashboard_service.today_dashboard(db, actor)
