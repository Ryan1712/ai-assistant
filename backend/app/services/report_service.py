import uuid
from datetime import date, datetime, time, timezone
from pathlib import Path

from fastapi import HTTPException
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Project, Report, Task, TaskAssignee, TaskStatus, TaskUpdate, User
from app.permissions import require_ceo

_ALL_COLUMNS = ["title", "project", "status", "percent", "assignees",
               "latest_update", "deadline"]
_COLUMN_HEADERS = {
    "title": "Tên task", "project": "Project", "status": "Trạng thái",
    "percent": "% hoàn thành", "assignees": "Người phụ trách",
    "latest_update": "Cập nhật mới nhất", "deadline": "Deadline",
}


def _append_text_row(sheet, row) -> None:
    """append() rồi ép mọi cell chuỗi thành text (data_type='s').

    openpyxl lưu chuỗi bắt đầu bằng '=' như công thức sống. Các cell ở đây
    có thể chứa dữ liệu do nhân viên nhập (nội dung update, full_name, tiêu
    đề task) nên phải chặn Excel formula injection khi CEO mở file.
    """
    sheet.append(row)
    for cell in sheet[sheet.max_row]:
        if isinstance(cell.value, str):
            cell.data_type = "s"


async def _latest_update_cell(db: AsyncSession, task_id: uuid.UUID) -> str:
    latest = (await db.execute(
        select(TaskUpdate).where(TaskUpdate.task_id == task_id)
        .order_by(TaskUpdate.created_at.desc(), TaskUpdate.id.desc()).limit(1)
    )).scalar_one_or_none()
    if latest is None:
        return ""
    return f"{latest.content} ({latest.created_at.strftime('%d/%m/%Y %H:%M')})"


async def generate_report(db: AsyncSession, actor: User, *,
                          project_id: uuid.UUID | None = None,
                          assignee_id: uuid.UUID | None = None,
                          date_from: date | None = None,
                          date_to: date | None = None,
                          status: TaskStatus | None = None,
                          columns: list[str] | None = None) -> dict:
    require_ceo(actor)
    columns = columns or _ALL_COLUMNS
    unknown = [c for c in columns if c not in _ALL_COLUMNS]
    if unknown:
        raise HTTPException(422, "invalid_column")
    if project_id is not None:
        project = await db.get(Project, project_id)
        if project is None or project.workspace_id != actor.workspace_id:
            raise HTTPException(404, "project_not_found")
    if assignee_id is not None:
        assignee = await db.get(User, assignee_id)
        if assignee is None or assignee.workspace_id != actor.workspace_id:
            raise HTTPException(404, "user_not_found")

    query = select(Task).where(Task.workspace_id == actor.workspace_id)
    if project_id is not None:
        query = query.where(Task.project_id == project_id)
    if assignee_id is not None:
        query = query.where(Task.id.in_(
            select(TaskAssignee.task_id).where(
                TaskAssignee.user_id == assignee_id,
                TaskAssignee.workspace_id == actor.workspace_id)))
    if date_from is not None:
        query = query.where(Task.created_at >= datetime.combine(
            date_from, time.min, tzinfo=timezone.utc))
    if date_to is not None:
        query = query.where(Task.created_at <= datetime.combine(
            date_to, time.max, tzinfo=timezone.utc))
    if status is not None:
        query = query.where(Task.status == status)
    tasks = list((await db.execute(query.order_by(Task.created_at.asc()))).scalars())

    wb = Workbook()
    sheet = wb.active
    sheet.title = "Tasks"
    _append_text_row(sheet, [_COLUMN_HEADERS[c] for c in columns])
    summary = {"total": len(tasks), **{s.value: 0 for s in TaskStatus}}
    for task in tasks:
        summary[task.status.value] += 1
        project_row = await db.get(Project, task.project_id)
        assignee_names = (await db.execute(
            select(User.full_name).join(TaskAssignee, TaskAssignee.user_id == User.id)
            .where(TaskAssignee.task_id == task.id))).scalars()
        row_values = {
            "title": task.title,
            "project": project_row.name if project_row else "",
            "status": task.status.value,
            "percent": task.percent,
            "assignees": ", ".join(assignee_names),
            "latest_update": await _latest_update_cell(db, task.id),
            "deadline": task.deadline.strftime("%d/%m/%Y") if task.deadline else "",
        }
        _append_text_row(sheet, [row_values[c] for c in columns])

    filters = {"project_id": str(project_id) if project_id else None,
               "assignee_id": str(assignee_id) if assignee_id else None,
               "date_from": date_from.isoformat() if date_from else None,
               "date_to": date_to.isoformat() if date_to else None,
               "status": status.value if status else None,
               "columns": columns}
    report = Report(workspace_id=actor.workspace_id, requested_by=actor.id,
                    filters=filters, summary=summary, file_path="")
    db.add(report)
    await db.flush()
    report.file_path = f"{actor.workspace_id}/{report.id}.xlsx"

    out = Path(get_settings().storage_dir) / report.file_path
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)

    await db.commit()
    return {"report_id": str(report.id), "summary": summary,
            "row_count": len(tasks), "filters_applied": filters}


async def list_reports(db: AsyncSession, actor: User) -> list[Report]:
    require_ceo(actor)
    rows = await db.execute(
        select(Report).where(Report.workspace_id == actor.workspace_id)
        .order_by(Report.created_at.desc())
    )
    return list(rows.scalars())
