from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import AddEmployeeIn, AddEmployeeOut
from app.services import auth_service

# Route cũ (tạo tài khoản + mã kích hoạt) tắt — sản phẩm quyết định 2026-07-26 chỉ
# CEO đăng nhập, nhân viên chỉ là record trong danh sách (add_employee bên dưới).
# Giữ router này (rỗng) để không phải sửa main.py; xem
# docs/superpowers/specs/2026-07-26-employee-as-list-design.md.
router = APIRouter(prefix="/api/v1/invites", tags=["invites"])

# @router.post("", response_model=CreateEmployeeOut, status_code=201)
# async def create_employee(
#     body: CreateEmployeeIn,
#     actor: User = Depends(get_current_user),
#     db: AsyncSession = Depends(get_db),
# ):
#     user, code, expires_at = await auth_service.create_employee(
#         db, actor=actor, email=body.email, full_name=body.full_name,
#         role=body.role.value, manager_id=body.manager_id,
#     )
#     return CreateEmployeeOut(user_id=user.id, email=user.email, full_name=user.full_name,
#                              role=user.role, activation_code=code, expires_at=expires_at)


employees_router = APIRouter(prefix="/api/v1/employees", tags=["employees"])


@employees_router.post("", response_model=AddEmployeeOut, status_code=201)
async def add_employee(
    body: AddEmployeeIn,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await auth_service.add_employee(
        db, actor=actor, full_name=body.full_name, email=body.email)
    return AddEmployeeOut(user_id=user.id, full_name=user.full_name, email=user.email)
