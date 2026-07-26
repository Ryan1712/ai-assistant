import uuid
from datetime import datetime
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.loop import resolve_confirmation
from app.agent.worker import enqueue_conversation
from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user
from app.models import (
    AgentTrace, ChatRequest, ChatRequestStatus, Conversation, Message, MessageRole,
    UsageLog, User,
)
from app.schemas import (
    ChatRequestEditIn, ChatRequestOut, ConfirmIn, ConversationCreateIn, ConversationOut,
    ConversationRenameIn, MessageOut, MessageSendIn, ReorderIn,
)
from app.services import continuity, embedding_service, session_service, voice_service

router = APIRouter(prefix="/api/v1/conversations", tags=["chat"])
chat_requests_router = APIRouter(prefix="/api/v1/chat-requests", tags=["chat"])

# TTL key hủy PHẢI >= arq job_timeout (600s, xem worker.py) — nếu nhỏ hơn, lệnh hủy
# có thể hết hạn trước khi loop kịp đọc trong 1 lượt stream dài.
_CANCEL_TTL = 600


async def get_arq_pool(request: Request):
    return request.app.state.arq_pool


@lru_cache
def get_redis():
    import redis.asyncio as redis_asyncio
    return redis_asyncio.from_url(get_settings().redis_url)


async def _get_owned_conversation_or_404(db: AsyncSession, actor: User,
                                         conversation_id: uuid.UUID) -> Conversation:
    conv = await db.get(Conversation, conversation_id)
    if conv is None or conv.workspace_id != actor.workspace_id or conv.user_id != actor.id:
        raise HTTPException(404, "conversation_not_found")
    return conv


@router.post("", response_model=ConversationOut, status_code=201)
async def create_conversation(body: ConversationCreateIn,
                              actor: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    conv = Conversation(workspace_id=actor.workspace_id, user_id=actor.id, title=body.title)
    db.add(conv)
    await db.commit()
    return conv


@router.get("", response_model=list[ConversationOut])
async def list_conversations(actor: User = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(Conversation).where(
        Conversation.workspace_id == actor.workspace_id, Conversation.user_id == actor.id,
    ).order_by(Conversation.created_at.desc()))
    return list(rows.scalars())


@router.get("/active", response_model=ConversationOut)
async def active_conversation(actor: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    from app.agent.llm_client import get_llm_client
    # llm_factory chỉ được gọi khi thật sự xoay (fold tail) — path không xoay
    # không dựng client thật, nên test /active không cần ANTHROPIC_API_KEY.
    conv = await session_service.get_or_rotate_active_conversation(
        db, actor, get_llm_client)
    return conv


@router.get("/timeline", response_model=list[MessageOut])
async def timeline(actor: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db),
                   before_at: datetime | None = Query(None),
                   before_id: uuid.UUID | None = Query(None),
                   limit: int = Query(50, ge=1, le=100)):
    """Một luồng liền mạch xuyên các conversation của actor (Phase 5). Newest-first,
    cursor = (before_at, before_id) của message cũ nhất trang trước. Chỉ conversation
    của chính actor."""
    conv_ids = select(Conversation.id).where(
        Conversation.workspace_id == actor.workspace_id,
        Conversation.user_id == actor.id)
    stmt = select(Message).where(Message.conversation_id.in_(conv_ids))
    if before_at is not None and before_id is not None:
        stmt = stmt.where(or_(
            Message.created_at < before_at,
            and_(Message.created_at == before_at, Message.id < before_id)))
    stmt = stmt.order_by(Message.created_at.desc(), Message.id.desc()).limit(limit)
    return list((await db.execute(stmt)).scalars().all())


@router.patch("/{conversation_id}", response_model=ConversationOut)
async def rename_conversation(conversation_id: uuid.UUID, body: ConversationRenameIn,
                              actor: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    conv = await _get_owned_conversation_or_404(db, actor, conversation_id)
    conv.title = body.title
    await db.commit()
    return conv


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: uuid.UUID,
                              actor: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    conv = await _get_owned_conversation_or_404(db, actor, conversation_id)
    # Xoá thủ công theo thứ tự FK con → cha (các FK conversation_id / chat_request_id
    # KHÔNG có ondelete=CASCADE). Nếu thêm bảng con mới tham chiếu chat_requests /
    # conversations, nhớ bổ sung ở đây.
    req_ids = select(ChatRequest.id).where(ChatRequest.conversation_id == conversation_id)
    await db.execute(delete(AgentTrace).where(AgentTrace.chat_request_id.in_(req_ids)))
    await db.execute(delete(UsageLog).where(UsageLog.chat_request_id.in_(req_ids)))
    await db.execute(delete(Message).where(Message.conversation_id == conversation_id))
    await db.execute(delete(ChatRequest).where(ChatRequest.conversation_id == conversation_id))
    await db.delete(conv)
    await db.commit()
    return Response(status_code=204)


@router.post("/{conversation_id}/messages", response_model=ChatRequestOut, status_code=201)
async def send_message(conversation_id: uuid.UUID, body: MessageSendIn,
                       actor: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db),
                       arq_pool=Depends(get_arq_pool)):
    conv = await _get_owned_conversation_or_404(db, actor, conversation_id)
    note_line = ""
    if body.voice_note_id is not None:
        # get_voice_note raise 404 nếu không phải chủ ghi âm / khác workspace —
        # danh tính từ JWT, không tin client.
        note = await voice_service.get_voice_note(db, actor, body.voice_note_id)
        label = note["title"] or (
            f"{note['duration_seconds']:.0f}s" if note["duration_seconds"] else "audio")
        note_line = (f"\n[Người dùng đính kèm 1 file ghi âm: \"{label}\" "
                     f"(voice_note_id: {body.voice_note_id}). Nếu không thấy transcript "
                     "ngay dưới dòng này nghĩa là hệ thống chưa bật nhận dạng giọng nói — "
                     "hãy nói thẳng điều đó, đừng bảo người dùng upload lại.]")
    if conv.title is None:
        # Tự đặt tên từ tin nhắn đầu — danh sách hội thoại toàn "chưa đặt tên" thì
        # không tìm lại được gì. Cắt 60 ký tự, gộp khoảng trắng.
        conv.title = " ".join(body.content.split())[:60]
    max_pos = (await db.execute(select(func.max(ChatRequest.queue_position)).where(
        ChatRequest.conversation_id == conv.id))).scalar()
    req = ChatRequest(workspace_id=actor.workspace_id, conversation_id=conv.id,
                      user_id=actor.id, content=body.content,
                      voice_note_id=body.voice_note_id,
                      queue_position=(max_pos or 0.0) + 1.0)
    db.add(req)
    await db.flush()
    user_msg = Message(workspace_id=actor.workspace_id, conversation_id=conv.id,
                       chat_request_id=req.id, role=MessageRole.user,
                       voice_note_id=body.voice_note_id,
                       content=[{"type": "text", "text": body.content + note_line}])
    db.add(user_msg)
    if conv.queue_held and continuity.is_resume_phrase(body.content):
        # 5.7: "tiếp tục công việc" → mở lại queue; request này vào cuối hàng
        # nên AI làm nốt việc cũ trước rồi mới trả lời nó.
        conv.queue_held = False
    await db.commit()
    # Phase 6 §10.3: index nguyên văn (không kèm note_line đính kèm ghi âm) —
    # "ký ức xuyên session" qua semantic_search, best-effort không chặn gửi tin.
    await embedding_service.index_content(db, actor.workspace_id, "chat_message",
                                          user_msg.id, body.content)
    await enqueue_conversation(arq_pool, conv.id)
    return req


async def _get_own_request_or_404(db: AsyncSession, actor: User,
                                  request_id: uuid.UUID) -> ChatRequest:
    req = await db.get(ChatRequest, request_id)
    if req is None or req.workspace_id != actor.workspace_id or req.user_id != actor.id:
        raise HTTPException(404, "request_not_found")
    return req


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(conversation_id: uuid.UUID,
                        actor: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    conv = await _get_owned_conversation_or_404(db, actor, conversation_id)
    rows = await db.execute(select(Message).where(Message.conversation_id == conv.id)
                            .order_by(Message.created_at.asc(), Message.id.asc()))
    return list(rows.scalars())


@router.get("/{conversation_id}/requests", response_model=list[ChatRequestOut])
async def list_requests(conversation_id: uuid.UUID,
                        actor: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    conv = await _get_owned_conversation_or_404(db, actor, conversation_id)
    rows = await db.execute(select(ChatRequest).where(
        ChatRequest.conversation_id == conv.id,
    ).order_by(ChatRequest.queue_position.asc()))
    return list(rows.scalars())


@router.post("/{conversation_id}/stop-all", status_code=204)
async def stop_all(conversation_id: uuid.UUID, actor: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db), redis=Depends(get_redis)):
    conv = await _get_owned_conversation_or_404(db, actor, conversation_id)
    rows = await db.execute(select(ChatRequest).where(
        ChatRequest.conversation_id == conv.id,
        ChatRequest.status.in_([ChatRequestStatus.queued, ChatRequestStatus.running,
                                ChatRequestStatus.deep_running]),
    ))
    for req in rows.scalars():
        if req.status == ChatRequestStatus.queued:
            req.status = ChatRequestStatus.cancelled
        else:
            await redis.set(f"cancel:{req.id}", "1", ex=_CANCEL_TTL)
    await db.commit()
    return Response(status_code=204)


@chat_requests_router.post("/{request_id}/confirm", response_model=ChatRequestOut)
async def confirm_request(request_id: uuid.UUID, body: ConfirmIn,
                          actor: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db),
                          arq_pool=Depends(get_arq_pool)):
    req = await _get_own_request_or_404(db, actor, request_id)
    if req.status != ChatRequestStatus.awaiting_confirmation:
        raise HTTPException(409, "not_awaiting_confirmation")
    await resolve_confirmation(db, req, approved=body.approved)
    await enqueue_conversation(arq_pool, req.conversation_id)
    return req


@chat_requests_router.patch("/{request_id}", response_model=ChatRequestOut)
async def edit_request(request_id: uuid.UUID, body: ChatRequestEditIn,
                       actor: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    req = await _get_own_request_or_404(db, actor, request_id)
    if req.status != ChatRequestStatus.queued:
        raise HTTPException(409, "not_queued")
    req.content = body.content
    msg = (await db.execute(select(Message).where(
        Message.chat_request_id == req.id, Message.role == MessageRole.user
    ))).scalar_one_or_none()
    if msg is not None:
        msg.content = [{"type": "text", "text": body.content}]
    await db.commit()
    return req


@chat_requests_router.post("/{request_id}/cancel", status_code=204)
async def cancel_request(request_id: uuid.UUID, actor: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db), redis=Depends(get_redis)):
    req = await _get_own_request_or_404(db, actor, request_id)
    if req.status == ChatRequestStatus.queued:
        req.status = ChatRequestStatus.cancelled
        await db.commit()
    elif req.status in (ChatRequestStatus.running, ChatRequestStatus.deep_running):
        await redis.set(f"cancel:{req.id}", "1", ex=_CANCEL_TTL)
    return Response(status_code=204)


@chat_requests_router.post("/{request_id}/reorder", response_model=ChatRequestOut)
async def reorder_request(request_id: uuid.UUID, body: ReorderIn,
                          actor: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    req = await _get_own_request_or_404(db, actor, request_id)
    if req.status != ChatRequestStatus.queued:
        raise HTTPException(409, "not_queued")
    siblings = (await db.execute(
        select(ChatRequest).where(ChatRequest.conversation_id == req.conversation_id,
                                  ChatRequest.status == ChatRequestStatus.queued,
                                  ChatRequest.id != req.id)
        .order_by(ChatRequest.queue_position.asc())
    )).scalars().all()
    if body.before_id is None:
        req.queue_position = (siblings[0].queue_position - 1.0) if siblings else 1.0
    else:
        idx = next((i for i, s in enumerate(siblings) if s.id == body.before_id), None)
        if idx is None:
            raise HTTPException(404, "before_request_not_found")
        before_pos = siblings[idx].queue_position
        prev_pos = siblings[idx - 1].queue_position if idx > 0 else before_pos - 2.0
        req.queue_position = (prev_pos + before_pos) / 2
    await db.commit()
    return req
