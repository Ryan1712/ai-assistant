"""Note — ghi chú CÁ NHÂN: ai tạo người đó thấy, CEO cũng không đọc note người khác
(khác task update/comment vốn là dữ liệu chung của task)."""
import uuid
from datetime import date

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Note, User
from app.permissions import get_visible_task_or_404, visible_project_ids
from app.services import embedding_service


async def create_note(db: AsyncSession, actor: User, content: str,
                      tags: list[str] | None = None, note_date: date | None = None,
                      task_id: uuid.UUID | None = None,
                      project_id: uuid.UUID | None = None) -> Note:
    if task_id is not None:
        await get_visible_task_or_404(db, actor, task_id)
    if project_id is not None and project_id not in await visible_project_ids(db, actor):
        raise HTTPException(404, "project_not_found")
    note = Note(workspace_id=actor.workspace_id, author_id=actor.id, content=content,
                tags=tags or [], task_id=task_id, project_id=project_id)
    if note_date is not None:
        note.note_date = note_date
    db.add(note)
    await db.commit()
    await embedding_service.index_content(db, actor.workspace_id, "note", note.id, content)
    return note


async def list_notes(db: AsyncSession, actor: User, on_date: date | None = None,
                     tag: str | None = None) -> list[Note]:
    query = select(Note).where(
        Note.workspace_id == actor.workspace_id, Note.author_id == actor.id,
    ).order_by(Note.created_at.desc())
    if on_date is not None:
        query = query.where(Note.note_date == on_date)
    rows = (await db.execute(query)).scalars().all()
    # tags là JSON column — lọc bằng Python cho portable (SQLite test / Postgres prod);
    # note luôn giới hạn theo 1 user nên tập kết quả nhỏ.
    if tag is not None:
        rows = [n for n in rows if tag in (n.tags or [])]
    return list(rows)
