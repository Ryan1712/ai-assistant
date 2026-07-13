"""Subscription mock (funtional-plan 6.10) — chưa gắn thanh toán, chỉ là khung
bật/tắt tính năng theo gói. Số liệu giới hạn Basic là tạm, sẽ chốt sau."""
import uuid

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, Skill, User, Workspace, WorkspacePlan

BASIC_LIMITS: dict[str, int] = {"projects": 5, "skills": 20, "members": 20}
ADVANCED_FEATURES: frozenset[str] = frozenset({"ceo_portal", "scheduled_reports"})

_COUNT_MODELS = {"projects": Project, "skills": Skill, "members": User}


def plan_allows(workspace: Workspace, feature: str) -> bool:
    if feature in ADVANCED_FEATURES:
        return workspace.plan == WorkspacePlan.advanced
    return True


async def enforce_limit(db: AsyncSession, workspace_id: uuid.UUID, kind: str) -> None:
    """403 plan_limit_reached nếu workspace gói Basic đã chạm hạn mức `kind`.
    Gọi TRƯỚC khi tạo mới project/skill/lời mời (member)."""
    ws = await db.get(Workspace, workspace_id)
    if ws is None or ws.plan == WorkspacePlan.advanced:
        return
    model = _COUNT_MODELS[kind]
    count = (await db.execute(
        select(func.count()).select_from(model).where(model.workspace_id == workspace_id)
    )).scalar_one()
    if count >= BASIC_LIMITS[kind]:
        raise HTTPException(403, "plan_limit_reached")
