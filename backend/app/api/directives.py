import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import CreateDirectiveIn, DirectiveOut, DirectiveQuestionIn, DirectiveRenegotiateIn
from app.services import directive_service

router = APIRouter(prefix="/api/v1/directives", tags=["directives"])


@router.post("", response_model=DirectiveOut, status_code=201)
async def create_directive(body: CreateDirectiveIn, actor: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    return await directive_service.create_directive(db, actor, **body.model_dump())


@router.get("", response_model=list[DirectiveOut])
async def list_directives(actor: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    result = await directive_service.get_directive_status(db, actor)
    return result["directives"]


@router.post("/{directive_id}/ack", response_model=DirectiveOut)
async def ack_directive(directive_id: uuid.UUID, actor: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    return await directive_service.ack_directive(db, actor, directive_id)


@router.post("/{directive_id}/question", response_model=DirectiveOut)
async def raise_question(directive_id: uuid.UUID, body: DirectiveQuestionIn,
                         actor: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    return await directive_service.raise_question(db, actor, directive_id, body.question_text)


@router.post("/{directive_id}/renegotiate", response_model=DirectiveOut)
async def renegotiate(directive_id: uuid.UUID, body: DirectiveRenegotiateIn,
                      actor: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    return await directive_service.renegotiate(
        db, actor, directive_id, body.reason,
        new_deadline_proposal=body.new_deadline_proposal)
