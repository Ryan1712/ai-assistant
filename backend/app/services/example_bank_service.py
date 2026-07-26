"""Example bank — "fine-tune bằng context" (spec AI upgrade §10.4).

CEO dạy AI cách xử lý 1 tình huống cụ thể bằng ví dụ (user_text +
ideal_behavior). Khi có yêu cầu tương tự NGỮ NGHĨA, build_example_block()
tiêm ví dụ liên quan nhất vào system prompt (block "# Ví dụ xử lý đúng")
để model bắt chước cách hành xử — cùng cơ chế semantic_search/RAG
(embedding_service), tái dùng bảng embeddings chung với
source_type="few_shot_example", KHÔNG cột embedding riêng trên
few_shot_examples.

FewShotExample.workspace_id NULL = ví dụ toàn cục — xem docstring model
trong models.py. add_example() (tool CEO dùng qua chat) CHỈ tạo được ví dụ
scope theo workspace của chính actor; build_example_block() nạp CẢ ví dụ
workspace của actor LẪN ví dụ global (workspace_id IS NULL).
"""
from __future__ import annotations

import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Embedding, FewShotExample, User
from app.permissions import require_ceo
from app.services import embedding_service

_EXAMPLE_MIN_SCORE = 0.15
_EXAMPLE_LIMIT = 3
_EXAMPLE_BLOCK_MAX_CHARS = 2500


async def index_example(db: AsyncSession, example: FewShotExample) -> None:
    """Index user_text của 1 ví dụ vào bảng embeddings chung. Ví dụ bất biến
    sau khi tạo (không có sửa) nên chỉ cần index 1 lần lúc tạo.

    Embedding.workspace_id là NOT NULL nhưng KHÔNG dùng để lọc quyền cho
    few_shot_example (build_example_block tự join ngược FewShotExample.
    workspace_id, kể cả NULL/global) — ví dụ global dùng UUID rỗng làm giá
    trị lấp chỗ, vô hại."""
    await embedding_service.index_content(
        db, example.workspace_id or uuid.UUID(int=0), "few_shot_example", example.id,
        example.user_text)


async def add_example(db: AsyncSession, actor: User, *, user_text: str,
                      ideal_behavior: str) -> dict:
    """CEO-only. LUÔN gắn workspace_id = actor.workspace_id — KHÔNG có đường
    nào từ đây tạo được ví dụ global (xem docstring module/model)."""
    require_ceo(actor)
    example = FewShotExample(workspace_id=actor.workspace_id, user_text=user_text.strip(),
                             ideal_behavior=ideal_behavior.strip())
    db.add(example)
    await db.commit()
    await index_example(db, example)
    return {"id": example.id, "workspace_id": str(example.workspace_id)}


async def build_example_block(db: AsyncSession, workspace_id: uuid.UUID, query: str) -> str:
    """Best-effort, KHÔNG BAO GIỜ raise — cùng pattern build_rag_context_block/
    active_memories_text, ghép vào dynamic_parts của system prompt."""
    text = (query or "").strip()
    if not text:
        return ""
    try:
        rows = (await db.execute(
            select(FewShotExample, Embedding)
            .join(Embedding, and_(Embedding.source_type == "few_shot_example",
                                  Embedding.source_id == FewShotExample.id))
            .where(or_(FewShotExample.workspace_id == workspace_id,
                      FewShotExample.workspace_id.is_(None)))
        )).all()
        if not rows:
            return ""
        query_vec = await embedding_service.get_embedding_client().embed(
            text[:embedding_service.MAX_CONTENT_CHARS])
        scored = []
        for example, emb in rows:
            score = embedding_service.cosine_similarity(query_vec, emb.embedding)
            if score >= _EXAMPLE_MIN_SCORE:
                scored.append((score, example))
        if not scored:
            return ""
        scored.sort(key=lambda pair: pair[0], reverse=True)

        lines = ["# Ví dụ xử lý đúng (CEO đã dạy — làm theo tinh thần này khi gặp tình "
                "huống tương tự, không nhất thiết đúng nguyên văn)"]
        for _, example in scored[:_EXAMPLE_LIMIT]:
            lines.append(f"- Tình huống: {example.user_text}\n  Cách xử lý đúng: "
                        f"{example.ideal_behavior}")
        block = "\n".join(lines)
        if len(block) > _EXAMPLE_BLOCK_MAX_CHARS:
            block = block[:_EXAMPLE_BLOCK_MAX_CHARS] + "\n(… cắt bớt)"
        return block
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "build_example_block fail cho workspace %s", workspace_id)
        return ""
