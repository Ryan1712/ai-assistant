import datetime as dt
import uuid

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.services import voice_service

router = APIRouter(prefix="/api/v1/voice-notes", tags=["voice-notes"])


async def get_arq_pool(request: Request):
    return request.app.state.arq_pool


@router.post("", status_code=201)
async def upload_voice_note(file: UploadFile = File(...), tags: str = Form(""),
                            title: str = Form(""),
                            duration_seconds: float | None = Form(None),
                            task_id: uuid.UUID | None = Form(None),
                            project_id: uuid.UUID | None = Form(None),
                            actor: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db),
                            arq_pool=Depends(get_arq_pool)):
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    data = await file.read()
    out = await voice_service.create_voice_note(
        db, actor, filename=file.filename or "", data=data, tags=tag_list,
        title=title.strip() or None, duration_seconds=duration_seconds,
        task_id=task_id, project_id=project_id)
    if out["transcript_status"] == "queued":
        # stt_mock=False: STT that duoc cau hinh -> can worker arq chay ngay,
        # khac voi "pending" (stt_mock=True) cho re-transcribe thu cong sau.
        await arq_pool.enqueue_job("transcribe_voice_note", uuid.UUID(out["id"]))
    return out


@router.post("/{voice_note_id}/transcribe", status_code=202)
async def retranscribe_voice_note(voice_note_id: uuid.UUID,
                                  actor: User = Depends(get_current_user),
                                  db: AsyncSession = Depends(get_db),
                                  arq_pool=Depends(get_arq_pool)):
    out = await voice_service.request_transcription(db, actor, voice_note_id)
    await arq_pool.enqueue_job("transcribe_voice_note", voice_note_id)
    return out


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
