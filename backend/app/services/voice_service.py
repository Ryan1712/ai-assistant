"""Voice note (funtional-plan 6.3) — ghi âm cá nhân như Note (author-only).

Transcription đứng sau TranscriptionClient; MockTranscriptionClient mặc định
(stt_mock=True) trả transcript rỗng + language "und" — real STT chờ chọn
provider (yêu cầu: tự nhận diện ngôn ngữ, không dịch).

File lưu {storage_dir}/voice/{workspace_id}/{uuid}{ext} — tên file sinh bằng
uuid, không dùng tên client gửi lên → không có path traversal.
"""
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Protocol

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import User, VoiceNote
from app.permissions import get_visible_task_or_404, visible_project_ids

_ALLOWED_EXTS = {".m4a", ".mp3", ".wav", ".aac", ".ogg", ".webm"}
_MAX_FILE_SIZE = 25 * 1024 * 1024  # attachment có trần 20MB; voice cho nhỉnh hơn
# Thị trường chính app là VN (UTC+7) — "on_date" từ client là ngày lịch theo giờ
# VN, không phải UTC; created_at lưu UTC nên phải quy đổi trước khi so ngày,
# tránh lệch ngày với ghi âm lúc 00:00-06:59 sáng giờ VN (cùng lớp bug với fix
# audit log ngày 2026-07-16).
_VN_TZ = timezone(timedelta(hours=7))


class TranscriptionClient(Protocol):
    async def transcribe(self, data: bytes, filename: str) -> tuple[str, str]:
        """Trả (transcript, language)."""
        ...


class MockTranscriptionClient:
    async def transcribe(self, data: bytes, filename: str) -> tuple[str, str]:
        return "", "und"


def get_transcription_client() -> TranscriptionClient:
    if get_settings().stt_mock:
        return MockTranscriptionClient()
    raise NotImplementedError("STT provider chưa được chọn — xem phụ lục funtional-plan")


def _voice_dir(workspace_id: uuid.UUID) -> Path:
    d = Path(get_settings().storage_dir) / "voice" / str(workspace_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _out(n: VoiceNote) -> dict:
    return {"id": str(n.id), "transcript": n.transcript, "language": n.language,
            "transcript_status": n.transcript_status,
            "title": n.title, "duration_seconds": n.duration_seconds,
            "tags": n.tags or [],
            "task_id": str(n.task_id) if n.task_id else None,
            "project_id": str(n.project_id) if n.project_id else None,
            "created_at": n.created_at}


async def create_voice_note(db: AsyncSession, actor: User, *, filename: str, data: bytes,
                            tags: list[str] | None = None,
                            task_id: uuid.UUID | None = None,
                            project_id: uuid.UUID | None = None,
                            title: str | None = None,
                            duration_seconds: float | None = None) -> dict:
    ext = Path(filename or "").suffix.lower()
    if ext not in _ALLOWED_EXTS:
        raise HTTPException(422, "unsupported_audio_format")
    if len(data) > _MAX_FILE_SIZE:
        raise HTTPException(413, "file_too_large")
    if task_id is not None:
        await get_visible_task_or_404(db, actor, task_id)
    if project_id is not None and project_id not in await visible_project_ids(db, actor):
        raise HTTPException(404, "project_not_found")

    file_path = _voice_dir(actor.workspace_id) / f"{uuid.uuid4()}{ext}"
    file_path.write_bytes(data)
    # Transcribe KHÔNG chạy đồng bộ ở đây nữa: STT thật sẽ chậm, block upload.
    # Worker arq xử lý (Task 16); khi chưa có STT thật thì status=pending, có thể
    # re-transcribe sau qua POST /voice-notes/{id}/transcribe.
    status = "queued" if not get_settings().stt_mock else "pending"
    note = VoiceNote(workspace_id=actor.workspace_id, author_id=actor.id,
                     file_path=str(file_path), transcript="", language="und",
                     transcript_status=status, title=title,
                     duration_seconds=duration_seconds,
                     tags=tags or [], task_id=task_id, project_id=project_id)
    db.add(note)
    await db.commit()
    return _out(note)


async def _get_own_or_404(db: AsyncSession, actor: User, voice_note_id: uuid.UUID) -> VoiceNote:
    note = await db.get(VoiceNote, voice_note_id)
    if (note is None or note.workspace_id != actor.workspace_id
            or note.author_id != actor.id):
        raise HTTPException(404, "voice_note_not_found")
    return note


async def list_voice_notes(db: AsyncSession, actor: User, tag: str | None = None,
                           on_date: date | None = None) -> list[dict]:
    rows = (await db.execute(select(VoiceNote).where(
        VoiceNote.workspace_id == actor.workspace_id, VoiceNote.author_id == actor.id,
    ).order_by(VoiceNote.created_at.desc()))).scalars().all()
    if tag is not None:
        rows = [n for n in rows if tag in (n.tags or [])]
    if on_date is not None:
        start = datetime.combine(on_date, time.min, tzinfo=_VN_TZ)
        end = start + timedelta(days=1)
        # SQLite (test) tra ve created_at naive du cot khai bao timezone=True —
        # gia tri luon la UTC (xem models._now), gan lai tzinfo truoc khi so sanh.
        rows = [n for n in rows
               if start <= (n.created_at if n.created_at.tzinfo else
                            n.created_at.replace(tzinfo=timezone.utc)) < end]
    return [_out(n) for n in rows]


async def get_voice_note(db: AsyncSession, actor: User, voice_note_id: uuid.UUID) -> dict:
    return _out(await _get_own_or_404(db, actor, voice_note_id))


async def get_file_path(db: AsyncSession, actor: User, voice_note_id: uuid.UUID) -> Path:
    note = await _get_own_or_404(db, actor, voice_note_id)
    path = Path(note.file_path)
    if not path.is_file():
        raise HTTPException(404, "file_not_found")
    return path
