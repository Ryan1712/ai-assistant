"""Distiller — bộ nhớ dài hạn công ty (spec AI upgrade §10.2 + §3 WorkspaceMemory).

Cron đêm (02:00 giờ VN): đọc TaskUpdate hôm đó của mỗi workspace có hoạt động,
1 lượt model_fast KHÔNG tool chưng cất tối đa 3 "sự thật đáng nhớ lâu dài",
dedup theo cosine similarity (tái dùng embedding_service — KHÔNG bảng riêng)
rồi ghi WorkspaceMemory. active_memories_text() nạp fact còn hiệu lực vào
system prompt (block "# Ghi nhớ dài hạn", app/agent/loop.py).

**Quyết định phạm vi cố ý hẹp hơn spec §3 (`WorkspaceMemory.scope`)**: v1 CHỈ
chưng cất từ `TaskUpdate` (dữ liệu công ty vốn đã chia sẻ theo `visible_task_ids`)
và LUÔN ghi `scope="workspace"` — KHÔNG đọc nội dung chat message của user để
tránh rủi ro rò rỉ: hội thoại của 1 nhân viên với AI là kênh riêng tư (mỗi user
1 luồng chat của chính mình), nếu đưa thẳng vào bộ nhớ "workspace" (mọi actor
đều nạp) thì vô tình biến lời nói riêng thành "sự thật chung" ai cũng thấy —
lệch nguyên tắc quyền đã có (note riêng tư, chat theo user). `scope="user:<uuid>"`
để schema sẵn cho mở rộng sau nếu cần chưng cất theo từng user, nhưng chưa
dùng ở v1.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm_client import LLMClient, TextDelta
from app.models import Embedding, TaskUpdate, User, WorkspaceMemory
from app.permissions import require_ceo
from app.services import embedding_service
from app.tz import VN_TZ

logger = logging.getLogger(__name__)

_DISTILL_SYSTEM = (
    "Bạn đọc các cập nhật tiến độ công việc trong 1 ngày của 1 công ty và chưng cất ra "
    "TỐI ĐA 3 sự thật/quyết định ĐÁNG NHỚ LÂU DÀI — KHÔNG phải chuyện vụn vặt hàng ngày "
    "(vd 1 quyết định đã chốt, 1 vấn đề lặp lại nhiều lần, 1 con số/mốc quan trọng, KHÔNG "
    "phải '% hoàn thành hôm nay'). Mỗi sự thật viết đúng 1 dòng, 1-2 câu tiếng Việt ngắn "
    "gọn, không đánh số/gạch đầu dòng. Nếu không có gì thật sự đáng nhớ lâu dài thì trả về "
    "đúng chữ KHÔNG, không thêm gì khác."
)
_MAX_FACTS_PER_RUN = 3
_MEMORY_DEDUP_MIN_SCORE = 0.85
_MEMORY_BLOCK_MAX_CHARS = 3200


async def _extract_facts(llm: LLMClient, texts: list[str]) -> list[str]:
    # Trần thô số dòng đưa vào prompt — chống 1 ngày quá nhiều update làm nổ context.
    joined = "\n".join(f"- {t}" for t in texts[:200])
    parts: list[str] = []
    async for event in llm.stream(
        system=_DISTILL_SYSTEM,
        messages=[{"role": "user", "content": [{"type": "text", "text": joined}]}],
        tools=[]):
        if isinstance(event, TextDelta):
            parts.append(event.text)
    reply = "".join(parts).strip()
    if not reply or reply.strip().upper() == "KHÔNG":
        return []
    lines = [ln.strip("-•* \t") for ln in reply.splitlines() if ln.strip()]
    return lines[:_MAX_FACTS_PER_RUN]


async def _is_duplicate(db: AsyncSession, workspace_id, scope: str, vector: list[float]) -> bool:
    rows = (await db.execute(
        select(Embedding).join(WorkspaceMemory, and_(
            WorkspaceMemory.id == Embedding.source_id,
            Embedding.source_type == "workspace_memory"))
        .where(WorkspaceMemory.workspace_id == workspace_id, WorkspaceMemory.scope == scope,
              WorkspaceMemory.archived_at.is_(None))
    )).scalars().all()
    return any(embedding_service.cosine_similarity(vector, e.embedding) >= _MEMORY_DEDUP_MIN_SCORE
              for e in rows)


async def _add_memory_if_not_duplicate(db: AsyncSession, workspace_id, scope: str,
                                       content: str, *, source: str) -> bool:
    vector = await embedding_service.get_embedding_client().embed(content)
    if await _is_duplicate(db, workspace_id, scope, vector):
        return False
    memory = WorkspaceMemory(workspace_id=workspace_id, scope=scope, content=content,
                             source=source)
    db.add(memory)
    await db.flush()
    db.add(Embedding(workspace_id=workspace_id, source_type="workspace_memory",
                     source_id=memory.id, chunk_no=0,
                     content=content[:embedding_service.MAX_CONTENT_CHARS], embedding=vector))
    await db.commit()
    return True


async def distill_workspace_memories(db: AsyncSession, llm: LLMClient, *,
                                     now: datetime | None = None) -> int:
    """Trả số fact mới đã thêm. Cron gọi mỗi phút (worker.py) — guard giờ nằm ở
    đây (02:00 VN), giống watcher_service.send_morning_briefs. 1 workspace lỗi
    (LLM down, embedding lỗi...) không được chặn workspace khác."""
    now = now or datetime.now(timezone.utc)
    now_vn = now.astimezone(VN_TZ)
    if not (now_vn.hour == 2 and now_vn.minute == 0):
        return 0

    day_start_vn = now_vn.replace(hour=0, minute=0, second=0, microsecond=0)
    day_start_utc = day_start_vn.astimezone(timezone.utc)

    ws_ids = list((await db.execute(
        select(TaskUpdate.workspace_id).where(TaskUpdate.created_at >= day_start_utc).distinct()
    )).scalars())

    count = 0
    for ws_id in ws_ids:
        try:
            updates = (await db.execute(select(TaskUpdate).where(
                TaskUpdate.workspace_id == ws_id, TaskUpdate.created_at >= day_start_utc,
            ).order_by(TaskUpdate.created_at.asc()))).scalars().all()
            texts = [u.content.strip() for u in updates if u.content and u.content.strip()]
            if not texts:
                continue
            facts = await _extract_facts(llm, texts)
            for fact in facts:
                if await _add_memory_if_not_duplicate(db, ws_id, "workspace", fact,
                                                       source="distiller"):
                    count += 1
        except Exception:
            logger.exception("distill fail cho workspace %s", ws_id)
            await db.rollback()
    return count


async def active_memories_text(db: AsyncSession, actor: User) -> str:
    """Best-effort, KHÔNG BAO GIỜ raise (cùng pattern snapshot_service) — ghép
    vào dynamic_parts của system prompt (app/agent/loop.py)."""
    try:
        now = datetime.now(timezone.utc)
        rows = (await db.execute(select(WorkspaceMemory).where(
            WorkspaceMemory.workspace_id == actor.workspace_id,
            WorkspaceMemory.archived_at.is_(None),
            or_(WorkspaceMemory.expires_at.is_(None), WorkspaceMemory.expires_at > now),
            or_(WorkspaceMemory.scope == "workspace", WorkspaceMemory.scope == f"user:{actor.id}"),
        ).order_by(WorkspaceMemory.created_at.desc()))).scalars().all()
        if not rows:
            return ""
        lines = ["# Ghi nhớ dài hạn"] + [f"- {m.content}" for m in rows]
        text = "\n".join(lines)
        if len(text) > _MEMORY_BLOCK_MAX_CHARS:
            text = text[:_MEMORY_BLOCK_MAX_CHARS] + "\n(… cắt bớt)"
        return text
    except Exception:
        logger.exception("active_memories_text fail cho actor %s", actor.id)
        return ""


async def list_memories(db: AsyncSession, actor: User) -> list[dict]:
    require_ceo(actor)
    rows = (await db.execute(select(WorkspaceMemory).where(
        WorkspaceMemory.workspace_id == actor.workspace_id,
        WorkspaceMemory.archived_at.is_(None),
    ).order_by(WorkspaceMemory.created_at.desc()))).scalars().all()
    return [{"id": m.id, "scope": m.scope, "content": m.content, "source": m.source,
            "created_at": m.created_at} for m in rows]


async def forget_memory(db: AsyncSession, actor: User, memory_id) -> None:
    require_ceo(actor)
    memory = await db.get(WorkspaceMemory, memory_id)
    if memory is None or memory.workspace_id != actor.workspace_id:
        raise HTTPException(404, "memory_not_found")
    memory.archived_at = datetime.now(timezone.utc)
    await db.commit()
