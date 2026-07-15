import uuid

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.services import attachment_service

router = APIRouter(prefix="/api/v1", tags=["attachments"])


@router.post("/tasks/{task_id}/attachments", status_code=201)
async def upload_attachment(task_id: uuid.UUID, file: UploadFile = File(...),
                            actor: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    data = await file.read()
    return await attachment_service.create_attachment(
        db, actor, task_id, filename=file.filename or "", data=data)


@router.get("/tasks/{task_id}/attachments")
async def list_attachments(task_id: uuid.UUID,
                           actor: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    return await attachment_service.list_attachments(db, actor, task_id)


@router.get("/attachments/{attachment_id}/file")
async def download_attachment(attachment_id: uuid.UUID,
                              actor: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    path = await attachment_service.get_file_path(db, actor, attachment_id)
    return FileResponse(path)
