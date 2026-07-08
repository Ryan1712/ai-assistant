from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas import AuthOut, LoginIn, RefreshIn, SignupInviteIn, SignupWorkspaceIn, TokenPairOut
from app.services import auth_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/signup-workspace", response_model=AuthOut, status_code=201)
async def signup_workspace(body: SignupWorkspaceIn, db: AsyncSession = Depends(get_db)):
    user, access, refresh = await auth_service.signup_workspace(db, **body.model_dump())
    return AuthOut(access_token=access, refresh_token=refresh, user=user)


@router.post("/signup-invite", response_model=AuthOut, status_code=201)
async def signup_invite(body: SignupInviteIn, db: AsyncSession = Depends(get_db)):
    user, access, refresh = await auth_service.signup_invite(db, **body.model_dump())
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
