import uuid

import jwt as pyjwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.db import get_db
from app.models import User, UserStatus


async def get_current_user(
    authorization: str = Header(default=""),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing_token")
    try:
        payload = security.decode_access_token(authorization.removeprefix("Bearer "))
    except pyjwt.InvalidTokenError:
        raise HTTPException(401, "invalid_token")
    user = await db.get(User, uuid.UUID(payload["sub"]))
    if user is None:
        raise HTTPException(401, "user_not_found")
    if user.status == UserStatus.locked:
        raise HTTPException(403, "account_locked")
    return user
