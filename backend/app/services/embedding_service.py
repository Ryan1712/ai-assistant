"""Semantic search / embeddings (Phase 6 spec AI upgrade §10.3).

Lưu embedding dạng JSON list[float] thay vì kiểu Vector của pgvector — test
suite chạy SQLite in-memory (tests/conftest.py), không có extension Postgres;
so khớp bằng cosine similarity thuần Python trên tập ứng viên ĐÃ lọc quyền
trước (đủ nhanh ở quy mô 1 workspace ~15-50 người, không cần ANN index) —
cùng lý do app/services/fuzzy_match.py chọn Jaccard-trigram thay vì pg_trgm.

Nguồn (note/task_update/comment/chat_message) đều bất biến sau khi tạo (không
có PATCH) nên index_content() chỉ cần insert-nếu-chưa-có, không cần
update-on-conflict. Quyền KHÔNG kiểm ở bảng embeddings — semantic_search()
luôn join ngược bảng gốc (đã lọc theo permissions.py) tại thời điểm truy vấn,
nên record gốc bị xóa/actor mất quyền thì tự động biến mất khỏi kết quả.
"""
from __future__ import annotations

import hashlib
import logging
import math
import uuid
from functools import lru_cache
from typing import Protocol

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, Embedding, Message, Note, Task, TaskComment, TaskUpdate, User
from app.permissions import visible_task_ids
from app.services.continuity import normalize_vn

logger = logging.getLogger(__name__)

EMBED_DIM = 1024
SEMANTIC_SEARCH_MIN_SCORE = 0.15
_MAX_CONTENT_CHARS = 4000
_SNIPPET_CHARS = 300
DEFAULT_LIMIT = 8

VALID_SOURCE_TYPES: frozenset[str] = frozenset(
    {"note", "task_update", "comment", "chat_message"})


class EmbeddingClient(Protocol):
    async def embed(self, text: str) -> list[float]: ...


class MockEmbeddingClient:
    """Hashing-trick bag-of-words — KHÔNG phải embedding ngữ nghĩa thật, nhưng
    đủ để cosine similarity phản ánh đúng số từ trùng nhau (dev/test dùng
    được semantic_search có ý nghĩa mà không cần API key — khác
    MockTranscriptionClient trả rỗng vì âm thanh không giả lập ý nghĩa được)."""

    async def embed(self, text: str) -> list[float]:
        vec = [0.0] * EMBED_DIM
        for word in normalize_vn(text).split():
            idx = int(hashlib.md5(word.encode()).hexdigest(), 16) % EMBED_DIM
            vec[idx] += 1.0
        norm = math.sqrt(sum(x * x for x in vec))
        if norm == 0:
            return vec
        return [x / norm for x in vec]


class VoyageEmbeddingClient:
    """Voyage `voyage-3.5` (tiếng Việt tốt, spec §0 đã chốt)."""

    _URL = "https://api.voyageai.com/v1/embeddings"

    async def embed(self, text: str) -> list[float]:
        import httpx

        from app.config import get_settings

        settings = get_settings()
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                self._URL,
                headers={"Authorization": f"Bearer {settings.embedding_api_key}"},
                json={"input": [text], "model": "voyage-3.5"},
            )
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]


mock_embedding_client = MockEmbeddingClient()


@lru_cache
def get_embedding_client() -> EmbeddingClient:
    from app.config import get_settings

    if get_settings().embedding_mock:
        return mock_embedding_client
    return VoyageEmbeddingClient()


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


async def index_content(db: AsyncSession, workspace_id: uuid.UUID, source_type: str,
                        source_id: uuid.UUID, content: str, *, chunk_no: int = 0) -> None:
    """Best-effort, KHÔNG BAO GIỜ raise — index lỗi (mạng, provider down...)
    không được phá write chính (cùng pattern notify()/push_service). Gọi SAU
    khi caller đã commit bản ghi gốc — transaction riêng, rollback ở đây chỉ
    ảnh hưởng chính lần index này."""
    text = (content or "").strip()
    if not text:
        return
    try:
        existing = await db.execute(select(Embedding.id).where(
            Embedding.source_type == source_type, Embedding.source_id == source_id,
            Embedding.chunk_no == chunk_no))
        if existing.first() is not None:
            return  # nguồn bất biến sau khi tạo — đã index rồi thì thôi
        truncated = text[:_MAX_CONTENT_CHARS]
        vector = await get_embedding_client().embed(truncated)
        db.add(Embedding(workspace_id=workspace_id, source_type=source_type,
                         source_id=source_id, chunk_no=chunk_no, content=truncated,
                         embedding=vector))
        await db.commit()
    except Exception:
        logger.exception("index_content fail cho %s %s", source_type, source_id)
        await db.rollback()


def _snippet(text: str) -> str:
    return text if len(text) <= _SNIPPET_CHARS else text[:_SNIPPET_CHARS] + "…"


async def _candidates_note(db: AsyncSession, actor: User) -> list[tuple[dict, list[float]]]:
    rows = await db.execute(
        select(Note, Embedding).join(
            Embedding, and_(Embedding.source_type == "note", Embedding.source_id == Note.id))
        .where(Note.workspace_id == actor.workspace_id, Note.author_id == actor.id))
    return [({"source_type": "note", "source_id": str(n.id), "content": _snippet(e.content),
             "note_date": n.note_date.isoformat(), "created_at": n.created_at.isoformat()},
            e.embedding) for n, e in rows.all()]


async def _candidates_task_update(db: AsyncSession, actor: User) -> list[tuple[dict, list[float]]]:
    ids = await visible_task_ids(db, actor)
    if not ids:
        return []
    rows = await db.execute(
        select(TaskUpdate, Task.title, Embedding).join(Task, TaskUpdate.task_id == Task.id)
        .join(Embedding, and_(Embedding.source_type == "task_update",
                              Embedding.source_id == TaskUpdate.id))
        .where(TaskUpdate.task_id.in_(ids)))
    return [({"source_type": "task_update", "source_id": str(u.id), "content": _snippet(e.content),
             "task_id": str(u.task_id), "task_title": title,
             "created_at": u.created_at.isoformat()}, e.embedding)
            for u, title, e in rows.all()]


async def _candidates_comment(db: AsyncSession, actor: User) -> list[tuple[dict, list[float]]]:
    ids = await visible_task_ids(db, actor)
    if not ids:
        return []
    rows = await db.execute(
        select(TaskComment, Task.title, Embedding).join(Task, TaskComment.task_id == Task.id)
        .join(Embedding, and_(Embedding.source_type == "comment",
                              Embedding.source_id == TaskComment.id))
        .where(TaskComment.task_id.in_(ids)))
    return [({"source_type": "comment", "source_id": str(c.id), "content": _snippet(e.content),
             "task_id": str(c.task_id), "task_title": title,
             "created_at": c.created_at.isoformat()}, e.embedding)
            for c, title, e in rows.all()]


async def _candidates_chat_message(db: AsyncSession, actor: User) -> list[tuple[dict, list[float]]]:
    rows = await db.execute(
        select(Message, Embedding).join(
            Embedding, and_(Embedding.source_type == "chat_message",
                            Embedding.source_id == Message.id))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.workspace_id == actor.workspace_id,
              Conversation.user_id == actor.id))
    return [({"source_type": "chat_message", "source_id": str(m.id), "content": _snippet(e.content),
             "conversation_id": str(m.conversation_id), "created_at": m.created_at.isoformat()},
            e.embedding) for m, e in rows.all()]


_CANDIDATE_FNS = {
    "note": _candidates_note,
    "task_update": _candidates_task_update,
    "comment": _candidates_comment,
    "chat_message": _candidates_chat_message,
}


async def semantic_search(db: AsyncSession, actor: User, query: str, *,
                          source_types: list[str] | None = None,
                          limit: int = DEFAULT_LIMIT) -> list[dict]:
    """Tìm theo NGỮ NGHĨA (khác search_service.search — ILIKE theo từ khóa đúng
    chuỗi con). Luôn lọc quyền tại thời điểm gọi (xem docstring module)."""
    types = [t for t in (source_types or sorted(VALID_SOURCE_TYPES)) if t in VALID_SOURCE_TYPES]
    if not types or not query.strip():
        return []
    query_vec = await get_embedding_client().embed(query.strip()[:_MAX_CONTENT_CHARS])

    scored: list[tuple[float, dict]] = []
    for t in types:
        for meta, vector in await _CANDIDATE_FNS[t](db, actor):
            score = _cosine(query_vec, vector)
            if score >= SEMANTIC_SEARCH_MIN_SCORE:
                scored.append((score, {**meta, "score": round(score, 4)}))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored[:limit]]
