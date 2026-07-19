"""Debug trace agent (Phase 0, spec AI upgrade 4.1) — soi 1 request AI đã chạy
những tool nào, mấy vòng, chậm ở đâu. Chỉ CEO; lọc workspace như mọi query."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import AgentTrace, User
from app.permissions import require_ceo
from app.schemas import AgentTraceOut

router = APIRouter(prefix="/api/v1/admin/traces", tags=["admin"])


@router.get("/{chat_request_id}", response_model=list[AgentTraceOut])
async def list_traces(chat_request_id: uuid.UUID,
                      actor: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    require_ceo(actor)
    rows = await db.execute(select(AgentTrace).where(
        AgentTrace.workspace_id == actor.workspace_id,
        AgentTrace.chat_request_id == chat_request_id,
    ).order_by(AgentTrace.created_at.asc()))
    return list(rows.scalars())
