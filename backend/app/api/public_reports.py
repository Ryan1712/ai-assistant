"""Router Public Reports API (funtional-plan §6.8, spec 2026-08-03-public-reports-api-design.md).

Đọc: qua bundle-id (không đăng nhập) hoặc JWT thường (dependency get_bundle_or_user).
Ghi: CEO qua JWT bình thường (get_current_user + require_ceo trong service layer).
"""
import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import PublicReportScope, get_bundle_or_user, get_current_user
from app.models import PublicReportStatus, User
from app.schemas import PublicReportOut, UpdatePublicReportIn
from app.services import public_report_service

router = APIRouter(prefix="/api/v1/public-reports", tags=["public-reports"])


# --- Đọc: bundle-id (không đăng nhập) hoặc JWT --------------------------

@router.get("", response_model=list[PublicReportOut])
async def list_public_reports(scope: PublicReportScope = Depends(get_bundle_or_user),
                              db: AsyncSession = Depends(get_db)):
    return await public_report_service.list_published(db, scope.workspace_id)


@router.get("/{report_id}", response_model=PublicReportOut)
async def get_public_report(report_id: uuid.UUID,
                            scope: PublicReportScope = Depends(get_bundle_or_user),
                            db: AsyncSession = Depends(get_db)):
    return await public_report_service.get_published(db, scope.workspace_id, report_id)


@router.get("/{report_id}/content")
async def get_public_report_content(report_id: uuid.UUID,
                                    scope: PublicReportScope = Depends(get_bundle_or_user),
                                    db: AsyncSession = Depends(get_db)):
    path, content_type = await public_report_service.get_content_path(
        db, scope.workspace_id, report_id)
    return FileResponse(path, media_type=content_type, headers={
        "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})


# --- Ghi: CEO qua JWT ----------------------------------------------------

@router.post("", response_model=PublicReportOut, status_code=201)
async def create_public_report(title: str = Form(...), description: str | None = Form(None),
                               file: UploadFile = File(...),
                               actor: User = Depends(get_current_user),
                               db: AsyncSession = Depends(get_db)):
    data = await file.read()
    return await public_report_service.create(
        db, actor, title=title, description=description,
        filename=file.filename or "", content_type=file.content_type or "application/octet-stream",
        data=data)


@router.patch("/{report_id}", response_model=PublicReportOut)
async def update_public_report(report_id: uuid.UUID, body: UpdatePublicReportIn,
                               actor: User = Depends(get_current_user),
                               db: AsyncSession = Depends(get_db)):
    return await public_report_service.update_metadata(
        db, actor, report_id, title=body.title, description=body.description)


@router.post("/{report_id}/publish", response_model=PublicReportOut)
async def publish_public_report(report_id: uuid.UUID,
                                actor: User = Depends(get_current_user),
                                db: AsyncSession = Depends(get_db)):
    return await public_report_service.set_status(
        db, actor, report_id, PublicReportStatus.published)


@router.post("/{report_id}/unpublish", response_model=PublicReportOut)
async def unpublish_public_report(report_id: uuid.UUID,
                                  actor: User = Depends(get_current_user),
                                  db: AsyncSession = Depends(get_db)):
    return await public_report_service.set_status(
        db, actor, report_id, PublicReportStatus.draft)


@router.delete("/{report_id}", status_code=204)
async def delete_public_report(report_id: uuid.UUID,
                               actor: User = Depends(get_current_user),
                               db: AsyncSession = Depends(get_db)):
    await public_report_service.delete(db, actor, report_id)
