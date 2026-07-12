from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app import plans
from app.db import get_db
from app.deps import get_current_user
from app.models import User, Workspace, WorkspacePlan
from app.permissions import require_ceo
from app.schemas import SubscriptionOut, SubscriptionPatchIn

router = APIRouter(prefix="/api/v1/subscription", tags=["subscription"])


def _out(ws: Workspace) -> dict:
    basic = ws.plan == WorkspacePlan.basic
    return {"plan": ws.plan.value, "limits": dict(plans.BASIC_LIMITS) if basic else None}


@router.get("", response_model=SubscriptionOut)
async def get_subscription(actor: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    return _out(await db.get(Workspace, actor.workspace_id))


@router.patch("", response_model=SubscriptionOut)
async def switch_plan(body: SubscriptionPatchIn, actor: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    # Mock: chỉ CEO đổi gói, không có thanh toán (funtional-plan 6.10)
    require_ceo(actor)
    ws = await db.get(Workspace, actor.workspace_id)
    ws.plan = body.plan
    await db.commit()
    return _out(ws)
