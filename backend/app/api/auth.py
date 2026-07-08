from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas import AuthOut, LoginIn, SignupWorkspaceIn
from app.services import auth_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/signup-workspace", response_model=AuthOut, status_code=201)
async def signup_workspace(body: SignupWorkspaceIn, db: AsyncSession = Depends(get_db)):
    user, access, refresh = await auth_service.signup_workspace(db, **body.model_dump())
    return AuthOut(access_token=access, refresh_token=refresh, user=user)


@router.post("/login", response_model=AuthOut)
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    user, access, refresh = await auth_service.login(db, **body.model_dump())
    return AuthOut(access_token=access, refresh_token=refresh, user=user)
