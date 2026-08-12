import dataclasses
import uuid

import jwt as pyjwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.config import get_settings
from app.db import get_db
from app.models import User, UserStatus

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(401, "missing_token")
    try:
        payload = security.decode_access_token(creds.credentials)
        user_id = uuid.UUID(payload["sub"])
    except (pyjwt.InvalidTokenError, KeyError, ValueError):
        raise HTTPException(401, "invalid_token")
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(401, "user_not_found")
    if user.status == UserStatus.locked:
        raise HTTPException(403, "account_locked")
    return user


@dataclasses.dataclass
class PublicReportScope:
    workspace_id: uuid.UUID
    user: User | None


async def get_bundle_or_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> PublicReportScope:
    settings = get_settings()
    bundle_id = request.headers.get("x-app-bundle-id")
    allowlist = {b.strip() for b in settings.public_app_bundle_ids.split(",") if b.strip()}
    if bundle_id and bundle_id in allowlist and settings.public_report_workspace_id:
        return PublicReportScope(
            workspace_id=uuid.UUID(settings.public_report_workspace_id), user=None)
    if creds is not None:
        user = await get_current_user(creds=creds, db=db)
        return PublicReportScope(workspace_id=user.workspace_id, user=user)
    raise HTTPException(401, "missing_token")
