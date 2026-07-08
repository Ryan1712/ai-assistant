import uuid

import jwt as pyjwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
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
