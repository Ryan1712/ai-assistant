from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import CreateEmployeeIn, CreateEmployeeOut
from app.services import auth_service

router = APIRouter(prefix="/api/v1/invites", tags=["invites"])


@router.post("", response_model=CreateEmployeeOut, status_code=201)
async def create_employee(
    body: CreateEmployeeIn,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user, code, expires_at = await auth_service.create_employee(
        db, actor=actor, email=body.email, full_name=body.full_name,
        role=body.role.value, manager_id=body.manager_id,
    )
    return CreateEmployeeOut(user_id=user.id, email=user.email, full_name=user.full_name,
                             role=user.role, activation_code=code, expires_at=expires_at)
