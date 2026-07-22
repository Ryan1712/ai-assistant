"""resolve_person/resolve_task (Phase 2 §6.3) — lớp dự phòng cho ca khó (trùng tên,
tên lạ) khi snapshot đã có danh bạ nhưng model vẫn cần tra cứu mờ. TUYỆT ĐỐI không
tự chọn khi >1 ứng viên — trả candidates để model hỏi lại đúng 1 câu."""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Task, TaskAssignee, User
from app.permissions import visible_task_ids, visible_user_ids
from app.services.fuzzy_match import match_score, pick_matches


def _user_out(u: User) -> dict:
    return {"id": str(u.id), "full_name": u.full_name, "role": u.role.value}


def _task_out(t: Task) -> dict:
    return {"id": str(t.id), "title": t.title, "status": t.status.value, "percent": t.percent,
            "deadline": t.deadline.isoformat() if t.deadline else None}


async def resolve_person(db: AsyncSession, actor: User, query: str) -> dict:
    ids = await visible_user_ids(db, actor)
    if not ids:
        return {"found": False, "candidates": [], "hint": "Không có ai trong phạm vi bạn thấy."}
    rows = await db.execute(select(User).where(User.id.in_(ids)))
    users = list(rows.scalars())
    scored = [(u, match_score(query, u.full_name)) for u in users]
    picked = pick_matches(scored)
    if not picked:
        return {"found": False, "candidates": [],
                "hint": f"Không tìm thấy ai tên gần giống '{query}'."}
    if len(picked) == 1:
        return {"found": True, "match": _user_out(picked[0][0])}
    return {"ambiguous": True, "candidates": [_user_out(u) for u, _ in picked],
            "hint": f"Có {len(picked)} người tên gần giống '{query}' — hỏi lại cụ thể là ai."}


async def resolve_task(db: AsyncSession, actor: User, query: str = "",
                       assignee_id: uuid.UUID | None = None) -> dict:
    if not query and not assignee_id:
        return {"error": "invalid_input", "hint": "Cần ít nhất query hoặc assignee_id để tra task."}
    ids = await visible_task_ids(db, actor)
    if not ids:
        return {"found": False, "candidates": [], "hint": "Không có task nào trong phạm vi bạn thấy."}
    stmt = select(Task).where(Task.id.in_(ids))
    if assignee_id is not None:
        stmt = stmt.join(TaskAssignee, TaskAssignee.task_id == Task.id).where(
            TaskAssignee.user_id == assignee_id)
    tasks = list((await db.execute(stmt)).scalars())
    if not tasks:
        return {"found": False, "candidates": [], "hint": "Không có task nào khớp phạm vi tra cứu."}
    if not query:
        # Không lọc chữ — assignee_id đã đủ thu hẹp, lấy toàn bộ task trong phạm vi đó.
        candidates = tasks
    else:
        picked = pick_matches([(t, match_score(query, t.title)) for t in tasks])
        candidates = [t for t, _ in picked]
    if not candidates:
        return {"found": False, "candidates": [],
                "hint": f"Không có task nào tên gần giống '{query}'."}
    if len(candidates) == 1:
        return {"found": True, "match": _task_out(candidates[0])}
    return {"ambiguous": True, "candidates": [_task_out(t) for t in candidates],
            "hint": f"Có {len(candidates)} task khớp — hỏi lại cụ thể task nào."}
