import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import NoteCreateIn, NoteOut
from app.services import note_service

router = APIRouter(prefix="/api/v1/notes", tags=["notes"])


@router.post("", response_model=NoteOut, status_code=201)
async def create_note(body: NoteCreateIn, actor: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    return await note_service.create_note(db, actor, **body.model_dump())


@router.get("", response_model=list[NoteOut])
async def list_notes(on_date: dt.date | None = None, tag: str | None = None,
                     actor: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    return await note_service.list_notes(db, actor, on_date=on_date, tag=tag)
