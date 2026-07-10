import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user
from app.models import Report, Role, User

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/{report_id}/download")
async def download_report(report_id: uuid.UUID,
                          actor: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    report = await db.get(Report, report_id)
    # 404 (không lộ tồn tại) cho cả: không có, khác workspace, không phải CEO
    if (report is None or report.workspace_id != actor.workspace_id
            or actor.role != Role.ceo):
        raise HTTPException(404, "report_not_found")
    path = Path(get_settings().storage_dir) / report.file_path
    if not path.is_file():
        raise HTTPException(404, "report_file_missing")
    return FileResponse(path, media_type=_XLSX,
                        filename=f"report-{report.id}.xlsx")
