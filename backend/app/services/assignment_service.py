"""Gợi ý người phù hợp khi giao task (2026-08-09) — spec
docs/superpowers/specs/2026-08-09-suggest-assignee-design.md.

Ưu tiên khớp chuyên môn (embedding_service.semantic_search trên
source_type="employee_expertise") trước; số task đang làm dở chỉ dùng để
tie-break khi nhiều người cùng hợp chuyên môn, hoặc làm fallback khi KHÔNG
ai khớp chuyên môn nào. KHÔNG tự động gán — chỉ trả gợi ý kèm lý do, CEO
vẫn xác nhận qua propose_actions như bình thường."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Task, TaskAssignee, TaskStatus, User
from app.permissions import require_ceo
from app.services import embedding_service

_MAX_SUGGESTIONS = 2


async def _count_open_tasks_by_user(db: AsyncSession, workspace_id: uuid.UUID) -> dict[str, int]:
    rows = await db.execute(
        select(TaskAssignee.user_id, func.count(Task.id))
        .join(Task, TaskAssignee.task_id == Task.id)
        .where(Task.workspace_id == workspace_id, Task.status != TaskStatus.done)
        .group_by(TaskAssignee.user_id))
    return {str(uid): count for uid, count in rows.all()}


async def suggest_assignee(db: AsyncSession, actor: User, *, task_title: str,
                           task_description: str = "") -> dict:
    require_ceo(actor)
    query = f"{task_title}\n{task_description}".strip()
    open_counts = await _count_open_tasks_by_user(db, actor.workspace_id)

    matches: list[dict] = []
    if query:
        matches = await embedding_service.semantic_search(
            db, actor, query, source_types=["employee_expertise"], limit=10)

    if matches:
        matches.sort(key=lambda m: (-m["score"], open_counts.get(m["source_id"], 0)))
        top = matches[:_MAX_SUGGESTIONS]
        user_ids = [uuid.UUID(m["source_id"]) for m in top]
        rows = await db.execute(select(User).where(User.id.in_(user_ids)))
        name_by_id = {str(u.id): u.full_name for u in rows.scalars()}
        suggestions = []
        for m in top:
            uid = m["source_id"]
            name = name_by_id.get(uid, m.get("full_name", "?"))
            n_open = open_counts.get(uid, 0)
            suggestions.append({
                "user_id": uid, "full_name": name,
                "reason": f"{name} có chuyên môn khớp với task này "
                         f"(độ khớp {m['score']:.2f}), đang có {n_open} task dở."})
        return {"suggestions": suggestions}

    # Fallback: không ai khớp chuyên môn -> người rảnh nhất toàn workspace.
    # Loại actor (CEO) khỏi ứng viên -- suggest_assignee gợi ý NHÂN VIÊN để
    # giao việc, không tự gợi ý chính người đang hỏi.
    rows = await db.execute(select(User).where(
        User.workspace_id == actor.workspace_id, User.id != actor.id))
    all_users = list(rows.scalars())
    if not all_users:
        return {"suggestions": [], "note": "Chưa có nhân viên nào trong workspace."}
    freest = min(all_users, key=lambda u: open_counts.get(str(u.id), 0))
    n_open = open_counts.get(str(freest.id), 0)
    return {"suggestions": [{
        "user_id": str(freest.id), "full_name": freest.full_name,
        "reason": f"Không có ai khớp chuyên môn task này — {freest.full_name} "
                 f"đang rảnh nhất ({n_open} task dở)."}]}
