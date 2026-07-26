"""Voice note (funtional-plan 6.3) — ghi âm cá nhân như Note (author-only).

Transcription đứng sau TranscriptionClient; MockTranscriptionClient mặc định
(stt_mock=True) trả transcript rỗng + language "und" — real STT chờ chọn
provider (yêu cầu: tự nhận diện ngôn ngữ, không dịch).

File lưu {storage_dir}/voice/{workspace_id}/{uuid}{ext} — tên file sinh bằng
uuid, không dùng tên client gửi lên → không có path traversal.
"""
import asyncio
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
from app.services import embedding_service

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


async def transcribe_note(db: AsyncSession, voice_note_id: uuid.UUID) -> None:
    """Chạy STT cho 1 voice note (gọi từ arq job, xem `transcribe_voice_note` trong
    worker.py). Không raise — lỗi STT ghi transcript_status="failed" để không chặn
    worker/arq retry vô ích; user re-transcribe thủ công qua request_transcription."""
    note = await db.get(VoiceNote, voice_note_id)
    if note is None:
        return
    note.transcript_status = "processing"
    await db.commit()
    try:
        data = Path(note.file_path).read_bytes()
        transcript, language = await get_transcription_client().transcribe(
            data, Path(note.file_path).name)
        note.transcript = transcript
        note.language = language
        note.transcript_status = "done"
    except Exception:
        note.transcript_status = "failed"
    await db.commit()
    if note.transcript_status == "done" and note.transcript:
        # Phase 6 §10.3: index_content() là upsert thật cho voice_transcript
        # (khác note/task_update bất biến) — retranscribe update tại chỗ.
        await embedding_service.index_content(db, note.workspace_id, "voice_transcript",
                                              note.id, note.transcript)


async def delete_voice_note(db: AsyncSession, actor: User, voice_note_id: uuid.UUID) -> None:
    note = await _get_own_or_404(db, actor, voice_note_id)
    try:
        Path(note.file_path).unlink(missing_ok=True)  # file hỏng/mất không chặn xóa row
    except OSError:
        pass
    await db.delete(note)
    await db.commit()


async def update_voice_note(db: AsyncSession, actor: User, voice_note_id: uuid.UUID, *,
                            title: str | None = None,
                            tags: list[str] | None = None) -> dict:
    note = await _get_own_or_404(db, actor, voice_note_id)
    if title is not None:
        note.title = title.strip() or None
    if tags is not None:
        note.tags = tags
    await db.commit()
    return _out(note)


async def request_transcription(db: AsyncSession, actor: User,
                                 voice_note_id: uuid.UUID) -> dict:
    """User bấm "nhận dạng lại" — chỉ khi có STT thật (stt_mock=False), nếu không
    trả 409 vì chạy lại cũng chỉ ra transcript rỗng như lúc tạo. Đưa note về
    queued; route gọi hàm này chịu trách nhiệm enqueue job arq theo sau."""
    note = await _get_own_or_404(db, actor, voice_note_id)
    if get_settings().stt_mock:
        raise HTTPException(409, "stt_not_configured")
    note.transcript_status = "queued"
    await db.commit()
    return {"id": str(note.id), "status": "queued"}


_TRANSCRIPT_MARK = "[Transcript ghi âm]"


async def inject_transcript_for_request(db: AsyncSession, req) -> None:
    """Trước khi agent chạy 1 request có đính kèm ghi âm: transcribe (nếu STT thật
    được bật và chưa done) rồi nối transcript vào user Message của request — nhờ đó
    MỌI lượt sau của conversation đều thấy nội dung qua _load_history, không cần
    cơ chế nhớ riêng. stt_mock=True thì bỏ qua (AI chỉ thấy dòng '[Đính kèm ghi âm...]')."""
    if req.voice_note_id is None or get_settings().stt_mock:
        return
    note = await db.get(VoiceNote, req.voice_note_id)
    if note is None:
        return
    if note.transcript_status in ("queued", "processing"):
        # Job transcribe nền (enqueue lúc upload) đang chạy — CHỜ thay vì gọi STT
        # lần 2 song song trên cùng file (tốn tiền + race ghi đè kết quả).
        for _ in range(30):
            await asyncio.sleep(3)
            await db.refresh(note)
            if note.transcript_status in ("done", "failed"):
                break
    elif note.transcript_status != "done":
        await transcribe_note(db, note.id)
        await db.refresh(note)
    if note.transcript_status != "done" or not note.transcript:
        return
    from app.models import Message, MessageRole

    msg = (await db.execute(select(Message).where(
        Message.chat_request_id == req.id, Message.role == MessageRole.user,
    ))).scalars().first()
    if msg is None:
        return
    if any(b.get("type") == "text" and _TRANSCRIPT_MARK in b.get("text", "")
           for b in msg.content):
        return  # idempotent — worker retry không nối trùng
    # JSON column: phải gán list MỚI thì SQLAlchemy mới thấy thay đổi, đừng .append
    msg.content = msg.content + [
        {"type": "text", "text": f"{_TRANSCRIPT_MARK}:\n{note.transcript}"}]
    await db.commit()
