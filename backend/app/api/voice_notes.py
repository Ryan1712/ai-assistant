import datetime as dt
import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.services import voice_service

router = APIRouter(prefix="/api/v1/voice-notes", tags=["voice-notes"])


@router.post("", status_code=201)
async def upload_voice_note(file: UploadFile = File(...), tags: str = Form(""),
                            task_id: uuid.UUID | None = Form(None),
                            project_id: uuid.UUID | None = Form(None),
                            actor: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    data = await file.read()
    return await voice_service.create_voice_note(
        db, actor, filename=file.filename or "", data=data, tags=tag_list,
        task_id=task_id, project_id=project_id)


@router.get("")
async def list_voice_notes(tag: str | None = None, on_date: dt.date | None = None,
                           actor: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    return await voice_service.list_voice_notes(db, actor, tag=tag, on_date=on_date)


@router.get("/{voice_note_id}")
async def get_voice_note(voice_note_id: uuid.UUID,
                         actor: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    return await voice_service.get_voice_note(db, actor, voice_note_id)


@router.get("/{voice_note_id}/file")
async def download_voice_note(voice_note_id: uuid.UUID,
                              actor: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    path = await voice_service.get_file_path(db, actor, voice_note_id)
    return FileResponse(path)
