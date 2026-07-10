import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.worker import enqueue_conversation
from app.db import get_db
from app.deps import get_current_user
from app.models import ChatRequest, Conversation, Message, MessageRole, User
from app.schemas import ChatRequestOut, ConversationCreateIn, ConversationOut, MessageSendIn

router = APIRouter(prefix="/api/v1/conversations", tags=["chat"])


async def get_arq_pool(request: Request):
    return request.app.state.arq_pool


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


@router.post("/{conversation_id}/messages", response_model=ChatRequestOut, status_code=201)
async def send_message(conversation_id: uuid.UUID, body: MessageSendIn,
                       actor: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db),
                       arq_pool=Depends(get_arq_pool)):
    conv = await _get_owned_conversation_or_404(db, actor, conversation_id)
    max_pos = (await db.execute(select(func.max(ChatRequest.queue_position)).where(
        ChatRequest.conversation_id == conv.id))).scalar()
    req = ChatRequest(workspace_id=actor.workspace_id, conversation_id=conv.id,
                      user_id=actor.id, content=body.content,
                      queue_position=(max_pos or 0.0) + 1.0)
    db.add(req)
    await db.flush()
    db.add(Message(workspace_id=actor.workspace_id, conversation_id=conv.id,
                   chat_request_id=req.id, role=MessageRole.user,
                   content=[{"type": "text", "text": body.content}]))
    await db.commit()
    await enqueue_conversation(arq_pool, conv.id)
    return req
