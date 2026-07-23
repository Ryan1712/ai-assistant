from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from functools import lru_cache

from app.config import get_settings
from app.db import get_db
from app.schemas import (
    ActivateAccountIn, AuthOut, ForgotPasswordIn, LoginIn, RefreshIn, ResetPasswordIn,
    SignupCodeIn, SignupWorkspaceIn, TokenPairOut, UnlockRequestIn,
)
from app.services import auth_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@lru_cache
def get_redis():
    import redis.asyncio as redis_asyncio
    return redis_asyncio.from_url(get_settings().redis_url)


@router.post("/signup-workspace", response_model=AuthOut, status_code=201)
async def signup_workspace(body: SignupWorkspaceIn, db: AsyncSession = Depends(get_db)):
    user, access, refresh = await auth_service.signup_workspace(db, **body.model_dump())
    return AuthOut(access_token=access, refresh_token=refresh, user=user)


@router.post("/activate", response_model=AuthOut, status_code=201)
async def activate(body: ActivateAccountIn, db: AsyncSession = Depends(get_db)):
    user, access, refresh = await auth_service.activate_account(db, **body.model_dump())
    return AuthOut(access_token=access, refresh_token=refresh, user=user)


@router.post("/signup-code", response_model=AuthOut, status_code=201)
async def signup_code(body: SignupCodeIn, db: AsyncSession = Depends(get_db)):
    user, access, refresh = await auth_service.signup_with_code(db, **body.model_dump())
    return AuthOut(access_token=access, refresh_token=refresh, user=user)


@router.post("/login", response_model=AuthOut)
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    user, access, refresh = await auth_service.login(db, **body.model_dump())
    return AuthOut(access_token=access, refresh_token=refresh, user=user)


@router.post("/refresh", response_model=TokenPairOut)
async def refresh(body: RefreshIn, db: AsyncSession = Depends(get_db)):
    _, access, new_refresh = await auth_service.rotate_refresh(db, body.refresh_token)
    return TokenPairOut(access_token=access, refresh_token=new_refresh)


@router.post("/logout", status_code=204)
async def logout(body: RefreshIn, db: AsyncSession = Depends(get_db)):
    await auth_service.revoke_refresh(db, body.refresh_token)
    return Response(status_code=204)


@router.post("/unlock-request", status_code=202)
async def unlock_request(body: UnlockRequestIn, db: AsyncSession = Depends(get_db)):
    await auth_service.request_unlock(db, email=body.email, device_uuid=body.device_uuid)
    return {"status": "accepted"}


@router.post("/forgot-password", status_code=202)
async def forgot_password(body: ForgotPasswordIn, db: AsyncSession = Depends(get_db),
                          redis=Depends(get_redis)):
    await auth_service.forgot_password(db, redis, email=body.email)
    return {"status": "accepted"}


@router.post("/reset-password", status_code=204)
async def reset_password(body: ResetPasswordIn, db: AsyncSession = Depends(get_db),
                         redis=Depends(get_redis)):
    await auth_service.reset_password(db, redis, email=body.email, code=body.code,
                                      new_password=body.new_password)
    return Response(status_code=204)
