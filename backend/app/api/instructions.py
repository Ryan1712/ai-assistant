import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import InstructionCreateIn, InstructionOut, InstructionUpdateIn
from app.services import instruction_service

router = APIRouter(prefix="/api/v1/instructions", tags=["instructions"])


@router.post("", response_model=InstructionOut, status_code=201)
async def create_instruction(body: InstructionCreateIn,
                             actor: User = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    ins = await instruction_service.create_instruction(db, actor, body.title, body.content)
    return {"id": ins.id, "title": ins.title, "version": ins.version, "content": body.content}


@router.get("", response_model=list[InstructionOut])
async def list_instructions(actor: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    return await instruction_service.list_instructions(db, actor)


@router.patch("/{instruction_id}")
async def update_instruction(instruction_id: uuid.UUID, body: InstructionUpdateIn,
                             actor: User = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    version = await instruction_service.update_instruction(db, actor, instruction_id,
                                                           body.content)
    return {"id": str(instruction_id), "version": version}


@router.delete("/{instruction_id}", status_code=204)
async def delete_instruction(instruction_id: uuid.UUID,
                             actor: User = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    await instruction_service.delete_instruction(db, actor, instruction_id)
    return Response(status_code=204)
