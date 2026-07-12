from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import PushTokenIn
from app.services import push_service

router = APIRouter(prefix="/api/v1/devices", tags=["devices"])


@router.put("/push-token")
async def register_push_token(body: PushTokenIn, actor: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    await push_service.register_push_token(db, actor, body.device_uuid, body.push_token)
    return {"status": "ok"}
