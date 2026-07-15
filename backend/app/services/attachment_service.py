"""Đính kèm tài liệu trong task (funtional-plan §8) — task_id bắt buộc, khác Note/VoiceNote.

File lưu {storage_dir}/attachments/{workspace_id}/{uuid}{ext} — tên file sinh bằng uuid,
không dùng tên client gửi lên cho đường dẫn thật (giống voice_service._voice_dir);
original_filename lưu riêng ở cột DB để hiển thị tên gốc cho người dùng.
"""
import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Attachment, User
from app.permissions import get_visible_task_or_404

_ALLOWED_EXTS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
                 ".txt", ".png", ".jpg", ".jpeg", ".zip"}
_MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB


def _attachment_dir(workspace_id: uuid.UUID) -> Path:
    d = Path(get_settings().storage_dir) / "attachments" / str(workspace_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _out(a: Attachment) -> dict:
    return {"id": str(a.id), "task_id": str(a.task_id), "author_id": str(a.author_id),
            "original_filename": a.original_filename, "file_size": a.file_size,
            "created_at": a.created_at}


async def create_attachment(db: AsyncSession, actor: User, task_id: uuid.UUID, *,
                            filename: str, data: bytes) -> dict:
    ext = Path(filename or "").suffix.lower()
    if ext not in _ALLOWED_EXTS:
        raise HTTPException(422, "unsupported_file_format")
    if len(data) > _MAX_FILE_SIZE:
        raise HTTPException(422, "file_too_large")
    task = await get_visible_task_or_404(db, actor, task_id)

    file_path = _attachment_dir(actor.workspace_id) / f"{uuid.uuid4()}{ext}"
    file_path.write_bytes(data)
    attachment = Attachment(workspace_id=actor.workspace_id, task_id=task.id,
                            author_id=actor.id, file_path=str(file_path),
                            original_filename=filename or "file", file_size=len(data))
    db.add(attachment)
    await db.commit()
    return _out(attachment)


async def list_attachments(db: AsyncSession, actor: User, task_id: uuid.UUID) -> list[dict]:
    task = await get_visible_task_or_404(db, actor, task_id)
    rows = await db.execute(select(Attachment).where(Attachment.task_id == task.id)
                            .order_by(Attachment.created_at.desc()))
    return [_out(a) for a in rows.scalars()]


async def get_file_path(db: AsyncSession, actor: User, attachment_id: uuid.UUID) -> Path:
    attachment = await db.get(Attachment, attachment_id)
    if attachment is None or attachment.workspace_id != actor.workspace_id:
        raise HTTPException(404, "attachment_not_found")
    await get_visible_task_or_404(db, actor, attachment.task_id)
    path = Path(attachment.file_path)
    if not path.is_file():
        raise HTTPException(404, "file_not_found")
    return path
