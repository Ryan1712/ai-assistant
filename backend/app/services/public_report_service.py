"""Public Reports API (funtional-plan §6.8, spec 2026-08-03-public-reports-api-design.md).

Đọc: qua bundle-id (không đăng nhập), chỉ report status=published, giới hạn 1
workspace cố định (PUBLIC_REPORT_WORKSPACE_ID). Ghi: CEO qua JWT bình thường.
Tách biệt hoàn toàn với Report/report_service.py (Excel tự sinh từ task nội bộ).
"""
import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import PublicReport, PublicReportStatus, User
from app.permissions import require_ceo

_MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB, giống attachment_service


def _dir(workspace_id: uuid.UUID) -> Path:
    d = Path(get_settings().storage_dir) / "public_reports" / str(workspace_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _out(r: PublicReport) -> dict:
    return {"id": str(r.id), "title": r.title, "description": r.description,
            "status": r.status.value, "content_type": r.content_type,
            "size_bytes": r.size_bytes, "created_at": r.created_at,
            "updated_at": r.updated_at}


async def list_published(db: AsyncSession, workspace_id: uuid.UUID) -> list[dict]:
    rows = await db.execute(
        select(PublicReport).where(PublicReport.workspace_id == workspace_id,
                                   PublicReport.status == PublicReportStatus.published)
        .order_by(PublicReport.created_at.desc()))
    return [_out(r) for r in rows.scalars()]


async def _get_published_row(db: AsyncSession, workspace_id: uuid.UUID,
                             report_id: uuid.UUID) -> PublicReport:
    report = await db.get(PublicReport, report_id)
    if (report is None or report.workspace_id != workspace_id
            or report.status != PublicReportStatus.published):
        raise HTTPException(404, "public_report_not_found")
    return report


async def get_published(db: AsyncSession, workspace_id: uuid.UUID,
                        report_id: uuid.UUID) -> dict:
    report = await _get_published_row(db, workspace_id, report_id)
    return _out(report)


async def get_content_path(db: AsyncSession, workspace_id: uuid.UUID,
                           report_id: uuid.UUID) -> tuple[Path, str]:
    report = await _get_published_row(db, workspace_id, report_id)
    path = Path(report.file_path)
    if not path.is_file():
        raise HTTPException(404, "public_report_file_missing")
    return path, report.content_type
