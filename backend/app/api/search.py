from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import SearchOut
from app.services import search_service

router = APIRouter(prefix="/api/v1/search", tags=["search"])


@router.get("", response_model=SearchOut)
async def search(q: str = Query(min_length=1), actor: User = Depends(get_current_user),
                 db: AsyncSession = Depends(get_db)):
    return await search_service.search(db, actor, q)
