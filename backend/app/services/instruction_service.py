"""Instruction — chỉ dẫn CEO soạn cho AI, versioned như Skill/SkillVersion.

Chỉ CEO tạo/sửa/xem/xóa. `active_instructions_text` KHÔNG check quyền vì được
agent loop gọi để build system prompt cho mọi user trong workspace (đọc DB mỗi
request nên cập nhật là "AI nạp lại ngay", không cần cache/invalidation).
"""
import uuid

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import plans
from app.models import Instruction, InstructionVersion, User
from app.permissions import require_ceo


async def _get_owned(db: AsyncSession, actor: User, instruction_id: uuid.UUID) -> Instruction:
    ins = await db.get(Instruction, instruction_id)
    if ins is None or ins.workspace_id != actor.workspace_id:
        raise HTTPException(404, "instruction_not_found")
    return ins


async def create_instruction(db: AsyncSession, actor: User, title: str, content: str) -> Instruction:
    require_ceo(actor)
    await plans.enforce_limit(db, actor.workspace_id, "instructions")
    ins = Instruction(workspace_id=actor.workspace_id, title=title, version=1,
                      created_by=actor.id)
    db.add(ins)
    await db.flush()
    db.add(InstructionVersion(workspace_id=actor.workspace_id, instruction_id=ins.id,
                              version=1, content=content, created_by=actor.id))
    await db.commit()
    return ins


async def update_instruction(db: AsyncSession, actor: User, instruction_id: uuid.UUID,
                             content: str) -> int:
    require_ceo(actor)
    ins = await _get_owned(db, actor, instruction_id)
    ins.version += 1
    db.add(InstructionVersion(workspace_id=actor.workspace_id, instruction_id=ins.id,
                              version=ins.version, content=content, created_by=actor.id))
    await db.commit()
    return ins.version


async def delete_instruction(db: AsyncSession, actor: User, instruction_id: uuid.UUID) -> None:
    require_ceo(actor)
    ins = await _get_owned(db, actor, instruction_id)
    await db.execute(delete(InstructionVersion).where(
        InstructionVersion.instruction_id == ins.id))
    await db.delete(ins)
    await db.commit()


async def _latest_contents(db: AsyncSession, workspace_id: uuid.UUID) -> list[tuple[Instruction, str]]:
    rows = await db.execute(
        select(Instruction, InstructionVersion.content)
        .join(InstructionVersion,
              (InstructionVersion.instruction_id == Instruction.id)
              & (InstructionVersion.version == Instruction.version))
        .where(Instruction.workspace_id == workspace_id)
        .order_by(Instruction.created_at.asc())
    )
    return [(ins, content) for ins, content in rows.all()]


async def list_instructions(db: AsyncSession, actor: User) -> list[dict]:
    require_ceo(actor)
    return [{"id": ins.id, "title": ins.title, "version": ins.version, "content": content}
            for ins, content in await _latest_contents(db, actor.workspace_id)]


_MAX_CHARS = 8000  # instruction nối thẳng vào system prompt MỌI request của MỌI nhân viên


async def active_instructions_text(db: AsyncSession, workspace_id: uuid.UUID) -> str:
    joined = "\n\n".join(f"## {ins.title}\n{content}"
                         for ins, content in await _latest_contents(db, workspace_id))
    if len(joined) > _MAX_CHARS:
        joined = joined[:_MAX_CHARS] + "\n\n(Chỉ dẫn quá dài — phần sau đã bị cắt.)"
    return joined
