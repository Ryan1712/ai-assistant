"""Phase 6 (onboarding): coach block — gợi ý ngắn cho CEO khi workspace còn thiếu
setup cơ bản. 4 cờ tính lại mỗi lượt (KHÔNG cache, KHÔNG lưu trạng thái "đã tốt
nghiệp") — rẻ vì tái dùng phần lớn từ build_workspace_data (Phase 1), chỉ thêm
đúng 1 query mới cho has_first_report.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Report
from app.services import snapshot_service

_COACH_LABELS = {
    "has_projects": "tạo project đầu tiên",
    "has_tasks": "thêm task vào project",
    "has_members": "mời thêm nhân viên/quản lý",
    "has_first_report": "tạo báo cáo đầu tiên",
}


async def get_coach_flags(db: AsyncSession, workspace_id: uuid.UUID) -> dict[str, bool]:
    data = await snapshot_service.build_workspace_data(db, workspace_id)
    has_projects = len(data["projects"]) > 0
    has_tasks = any(p["task_total"] > 0 for p in data["projects"])
    has_members = len(data["users"]) > 1  # CEO tự thân đã nằm trong danh sách này
    has_first_report = (await db.execute(
        select(Report.id).where(Report.workspace_id == workspace_id).limit(1)
    )).scalar_one_or_none() is not None
    return {"has_projects": has_projects, "has_tasks": has_tasks,
           "has_members": has_members, "has_first_report": has_first_report}


def render_coach_block(flags: dict[str, bool]) -> str | None:
    """None nếu đủ cả 4 mốc — không có gì để gợi ý, khối tự biến mất khỏi system
    prompt (không cần code riêng để 'tắt hẳn')."""
    missing = [_COACH_LABELS[k] for k, v in flags.items() if not v]
    if not missing:
        return None
    items = ", ".join(missing)
    return (
        "# Gợi ý dẫn dắt (chỉ hiện với CEO chưa hoàn tất thiết lập)\n"
        f"Công ty còn thiếu: {items}. Sau câu trả lời chính, thêm ĐÚNG 1 câu ngắn "
        "gợi ý bước tiếp theo hợp lý (chọn 1 trong các việc còn thiếu ở trên, dựa "
        "theo ngữ cảnh câu hỏi vừa rồi). Không lặp lại gợi ý y hệt câu trước nếu "
        "ngữ cảnh không đổi."
    )
