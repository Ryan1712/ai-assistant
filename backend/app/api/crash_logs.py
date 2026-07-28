"""crash_logs.py — Router crash-log reporting (Sprint 1, Task 1.1)

3 endpoints:
  POST /api/v1/crash-logs          — batch ingest (mọi user đăng nhập)
  GET  /api/v1/crash-logs          — danh sách chi tiết (chỉ CEO)
  GET  /api/v1/crash-logs/summary  — tổng hợp theo fingerprint (chỉ CEO)

Router chỉ xử lý HTTP: validate input, gọi service, trả response.
Toàn bộ logic + kiểm quyền nằm ở crash_service.py.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import (
    CrashIngestOut,
    CrashLogBatchIn,
    CrashLogListOut,
    CrashSummaryOut,
)
from app.services import crash_service

router = APIRouter(prefix="/api/v1/crash-logs", tags=["crash-logs"])


@router.post("", response_model=CrashIngestOut)
async def ingest_crash_logs(
    request: Request,
    body: CrashLogBatchIn,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CrashIngestOut:
    """Nhận batch crash log từ FE/BE agent.

    Không cần quyền đặc biệt — mọi user đăng nhập đều gửi được.
    workspace_id/user_id lấy từ JWT của actor, không tin body.
    Rate limit: 60 bản ghi / user / 5 phút (in-memory trên app.state).
    """
    rate_store = getattr(request.app.state, "crash_rate_limit", None)
    result = await crash_service.ingest_batch(
        db=db,
        actor=actor,
        items=body.items,
        rate_store=rate_store,
    )
    return CrashIngestOut(**result)


@router.get("/summary", response_model=CrashSummaryOut)
async def get_crash_summary(
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CrashSummaryOut:
    """Tổng hợp crash theo fingerprint — chỉ CEO.

    Trả về: fingerprint, số lần xảy ra, số user bị ảnh hưởng,
    lần đầu, lần cuối, message mẫu, source.
    """
    result = await crash_service.summarize(db=db, actor=actor)
    return CrashSummaryOut(**result)


@router.get("", response_model=CrashLogListOut)
async def list_crash_logs(
    page: int = 1,
    size: int = 50,
    source: str | None = None,
    platform: str | None = None,
    fingerprint: str | None = None,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CrashLogListOut:
    """Danh sách crash log chi tiết — chỉ CEO.

    Luôn lọc theo workspace_id của actor (JWT).
    Hỗ trợ phân trang và lọc theo source/platform/fingerprint.
    """
    result = await crash_service.list_crashes(
        db=db,
        actor=actor,
        page=page,
        size=size,
        source=source,
        platform=platform,
        fingerprint=fingerprint,
    )
    return CrashLogListOut(**result)
