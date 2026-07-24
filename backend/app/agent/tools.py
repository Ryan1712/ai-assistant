from __future__ import annotations

import uuid
from datetime import date, datetime
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal

from fastapi import HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Role, TaskStatus, User
from app.schemas import (
    CommentCreateIn, ProjectCreateIn, ProjectPatchIn, SkillCreateIn, SkillGrantIn,
    SkillVersionIn, TaskCreateIn, TaskPatchIn, TaskUpdateCreateIn,
)
from app.services import (
    analytics_service, attachment_service, audit_service, auth_service, dashboard_service,
    directive_service, distiller_service, email_service, embedding_service, instruction_service,
    note_service, notification_service, portal_service, report_schedule_service, report_service,
    resolver_service, search_service, skill_service, voice_service, work_service,
)


@dataclass
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[[AsyncSession, User, BaseModel], Awaitable[dict]]
    sensitive: bool = False

    @property
    def input_schema(self) -> dict:
        schema = self.input_model.model_json_schema()
        schema.pop("title", None)
        return schema


TOOLS: dict[str, ToolSpec] = {}


def _register(name: str, description: str, input_model: type[BaseModel],
              handler: Callable, sensitive: bool = False) -> None:
    TOOLS[name] = ToolSpec(name=name, description=description, input_model=input_model,
                          handler=handler, sensitive=sensitive)


_ERROR_LABELS = {403: "forbidden", 404: "not_found", 422: "invalid_input"}
_ERROR_MESSAGES = {
    403: "Bạn không có quyền làm điều này.",
    404: "Không tìm thấy đối tượng được yêu cầu.",
    422: "Dữ liệu đầu vào không hợp lệ.",
}
_ERROR_HINTS = {
    403: "Việc này ngoài quyền — báo người dùng nhờ CEO/quản lý, đừng thử tool khác để lách.",
    404: "Không tìm thấy đối tượng — id có thể sai/đã bị xóa; gọi list_* tương ứng để tra lại id đúng.",
    422: "Tham số chưa hợp lệ — sửa theo input_schema của tool rồi gọi lại.",
}


async def call_tool(db: AsyncSession, actor: User, tool_name: str, tool_input: dict) -> dict:
    """Gọi 1 tool theo tên; lỗi service (HTTPException) bọc thành tool_result lỗi, không raise ra ngoài."""
    if tool_name not in TOOLS:
        return {"error": "not_found", "hint": f"Tool '{tool_name}' không tồn tại — gọi lại với tên tool đúng."}
    spec = TOOLS[tool_name]
    try:
        parsed = spec.input_model(**tool_input)
    except Exception as exc:
        return {"error": "invalid_input", "message": f"Dữ liệu đầu vào không hợp lệ: {exc}",
                "hint": _ERROR_HINTS[422]}
    try:
        return await spec.handler(db, actor, parsed)
    except HTTPException as exc:
        label = _ERROR_LABELS.get(exc.status_code, "error")
        message = _ERROR_MESSAGES.get(exc.status_code, str(exc.detail))
        hint = _ERROR_HINTS.get(exc.status_code, "Xem message.")
        return {"error": label, "message": message, "hint": hint}
    except Exception as exc:  # noqa: BLE001
        # Lỗi lập trình/hạ tầng trong 1 tool không được giết cả request — trả về
        # tool_result lỗi để model tự báo lại/thử cách khác.
        return {"error": "tool_failed",
                "message": f"Tool gặp lỗi hệ thống ({type(exc).__name__}): {exc}",
                "hint": "Lỗi hệ thống — báo người dùng và không thử lại lặp lại tool này."}


class NoArgsIn(BaseModel):
    pass


class UpdateProjectToolIn(ProjectPatchIn):
    project_id: uuid.UUID


class GetTaskToolIn(BaseModel):
    task_id: uuid.UUID


class UpdateTaskToolIn(TaskPatchIn):
    task_id: uuid.UUID


class AssignTaskToolIn(BaseModel):
    task_id: uuid.UUID
    user_id: uuid.UUID


class UnassignTaskToolIn(BaseModel):
    task_id: uuid.UUID
    user_id: uuid.UUID


class DeleteTaskToolIn(BaseModel):
    task_id: uuid.UUID


class DeleteProjectToolIn(BaseModel):
    project_id: uuid.UUID


async def _create_project(db, actor, body: ProjectCreateIn) -> dict:
    project = await work_service.create_project(db, actor, **body.model_dump())
    return {"id": str(project.id), "name": project.name, "status": project.status}


async def _update_project(db, actor, body: UpdateProjectToolIn) -> dict:
    patch = body.model_dump(exclude={"project_id"}, exclude_unset=True)
    project = await work_service.update_project(db, actor, body.project_id, patch)
    return {"id": str(project.id), "name": project.name, "status": project.status}


async def _list_projects(db, actor, body: NoArgsIn) -> dict:
    projects = await work_service.list_projects(db, actor)
    result = {"projects": [{"id": str(p.id), "name": p.name, "status": p.status} for p in projects]}
    if not projects:
        result["note"] = "Workspace chưa có project nào trong phạm vi bạn thấy."
    return result


async def _create_task(db, actor, body: TaskCreateIn) -> dict:
    task = await work_service.create_task(db, actor, **body.model_dump())
    return {"id": str(task["id"]), "title": task["title"], "status": task["status"].value}


async def _update_task(db, actor, body: UpdateTaskToolIn) -> dict:
    patch = body.model_dump(exclude={"task_id"}, exclude_unset=True)
    task = await work_service.update_task(db, actor, body.task_id, patch)
    return {"id": str(task["id"]), "title": task["title"], "status": task["status"].value,
           "percent": task["percent"]}


async def _list_tasks(db, actor, body: NoArgsIn) -> dict:
    tasks = await work_service.list_tasks(db, actor)
    result = {"tasks": [{"id": str(t["id"]), "title": t["title"], "status": t["status"].value,
                         "percent": t["percent"]} for t in tasks]}
    if not tasks:
        result["note"] = "Workspace chưa có task nào trong phạm vi bạn thấy."
    return result


async def _get_task(db, actor, body: GetTaskToolIn) -> dict:
    task = await work_service.get_task(db, actor, body.task_id)
    return {"id": str(task["id"]), "title": task["title"], "description": task["description"],
           "status": task["status"].value, "percent": task["percent"],
           "assignee_ids": [str(u) for u in task["assignee_ids"]]}


async def _assign_task(db, actor, body: AssignTaskToolIn) -> dict:
    created = await work_service.assign_task(db, actor, body.task_id, body.user_id)
    return {"task_id": str(body.task_id), "user_id": str(body.user_id), "already_assigned": not created}


async def _unassign_task(db, actor, body: UnassignTaskToolIn) -> dict:
    await work_service.unassign_task(db, actor, body.task_id, body.user_id)
    return {"task_id": str(body.task_id), "user_id": str(body.user_id), "unassigned": True}


_register("create_project", "Tạo project mới (chỉ CEO).", ProjectCreateIn, _create_project)
_register("update_project", "Sửa project theo id (chỉ CEO).", UpdateProjectToolIn, _update_project)
_register("list_projects", "Liệt kê project mà actor được thấy.", NoArgsIn, _list_projects)
_register("create_task", "Tạo task trong 1 project (chỉ CEO).", TaskCreateIn, _create_task)
_register("update_task", "Sửa task theo id (chỉ CEO).", UpdateTaskToolIn, _update_task)
_register("list_tasks", "Liệt kê task mà actor được thấy.", NoArgsIn, _list_tasks)
_register("get_task", "Xem chi tiết 1 task theo id.", GetTaskToolIn, _get_task)
_register("assign_task", "Gán 1 người vào task (chỉ CEO).", AssignTaskToolIn, _assign_task)
_register("unassign_task", "Bỏ gán 1 người khỏi task (chỉ CEO).", UnassignTaskToolIn, _unassign_task)


async def _delete_task(db, actor, body: DeleteTaskToolIn) -> dict:
    await work_service.delete_task(db, actor, body.task_id)
    return {"deleted": True}


async def _delete_project(db, actor, body: DeleteProjectToolIn) -> dict:
    await work_service.delete_project(db, actor, body.project_id)
    return {"deleted": True}


_register("delete_task", "Xóa vĩnh viễn 1 task (chỉ CEO; xóa cả bình luận/cập nhật/"
          "đính kèm của nó).", DeleteTaskToolIn, _delete_task, sensitive=True)
_register("delete_project", "Xóa vĩnh viễn 1 project VÀ TOÀN BỘ task bên trong "
          "(chỉ CEO).", DeleteProjectToolIn, _delete_project, sensitive=True)


class AddTaskUpdateToolIn(TaskUpdateCreateIn):
    task_id: uuid.UUID


class ListTaskUpdatesToolIn(BaseModel):
    task_id: uuid.UUID


class AddCommentToolIn(CommentCreateIn):
    task_id: uuid.UUID


class ListCommentsToolIn(BaseModel):
    task_id: uuid.UUID


class AddSkillVersionToolIn(SkillVersionIn):
    skill_id: uuid.UUID


class GrantSkillToolIn(SkillGrantIn):
    skill_id: uuid.UUID


class UseSkillToolIn(BaseModel):
    skill_id: uuid.UUID


class ListSkillGrantsToolIn(BaseModel):
    skill_id: uuid.UUID


class RevokeSkillGrantToolIn(BaseModel):
    skill_id: uuid.UUID
    user_id: uuid.UUID


def _skill_tool_out(skill: dict) -> dict:
    return {"id": str(skill["id"]), "name": skill["name"], "kind": skill["kind"].value,
           "task_id": str(skill["task_id"]) if skill["task_id"] else None,
           "latest_version": skill["latest_version"]}


async def _add_task_update(db, actor, body: AddTaskUpdateToolIn) -> dict:
    patch = body.model_dump(exclude={"task_id"})
    upd = await work_service.add_task_update(db, actor, body.task_id, **patch)
    return {"id": str(upd.id), "task_id": str(upd.task_id), "percent": upd.percent,
           "status": upd.status.value if upd.status else None}


async def _list_task_updates(db, actor, body: ListTaskUpdatesToolIn) -> dict:
    updates = await work_service.list_task_updates(db, actor, body.task_id)
    result = {"updates": [{"id": str(u.id), "author_id": str(u.author_id), "content": u.content,
                           "percent": u.percent, "created_at": u.created_at.isoformat()}
                          for u in updates]}
    if not updates:
        result["note"] = "Task này chưa có cập nhật tiến độ nào."
    return result


async def _add_comment(db, actor, body: AddCommentToolIn) -> dict:
    comment = await work_service.add_comment(db, actor, body.task_id, body.content)
    return {"id": str(comment["id"]), "task_id": str(comment["task_id"]), "content": comment["content"]}


async def _list_comments(db, actor, body: ListCommentsToolIn) -> dict:
    comments = await work_service.list_comments(db, actor, body.task_id)
    result = {"comments": [{"id": str(c["id"]), "author_id": str(c["author_id"]), "content": c["content"],
                            "created_at": c["created_at"].isoformat()} for c in comments]}
    if not comments:
        result["note"] = "Task này chưa có bình luận nào."
    return result


async def _create_skill(db, actor, body: SkillCreateIn) -> dict:
    skill = await skill_service.create_skill(db, actor, **body.model_dump())
    return _skill_tool_out(skill)


async def _add_skill_version(db, actor, body: AddSkillVersionToolIn) -> dict:
    version = await skill_service.add_version(db, actor, body.skill_id, body.content)
    return {"skill_id": str(body.skill_id), "version": version}


async def _grant_skill(db, actor, body: GrantSkillToolIn) -> dict:
    created = await skill_service.grant_skill(db, actor, body.skill_id, body.user_id)
    return {"skill_id": str(body.skill_id), "user_id": str(body.user_id),
           "already_granted": not created}


async def _list_skills(db, actor, body: NoArgsIn) -> dict:
    skills = await skill_service.list_skills(db, actor)
    result = {"skills": [_skill_tool_out(s) for s in skills]}
    if not skills:
        result["note"] = "Chưa có skill nào actor được thấy/được cấp."
    return result


async def _use_skill(db, actor, body: UseSkillToolIn) -> dict:
    return await skill_service.use_skill(db, actor, body.skill_id)


async def _list_skill_grants(db, actor, body: ListSkillGrantsToolIn) -> dict:
    grants = await skill_service.list_grants(db, actor, body.skill_id)
    result = {"grants": grants}
    if not grants:
        result["note"] = "Skill này chưa cấp cho ai."
    return result


async def _revoke_skill_grant(db, actor, body: RevokeSkillGrantToolIn) -> dict:
    await skill_service.revoke_grant(db, actor, body.skill_id, body.user_id)
    return {"skill_id": str(body.skill_id), "user_id": str(body.user_id), "revoked": True}


_register("add_task_update", "Cập nhật tiến độ 1 task (% và/hoặc trạng thái).",
          AddTaskUpdateToolIn, _add_task_update)
_register("list_task_updates", "Lịch sử cập nhật tiến độ của 1 task, mới nhất trước.",
          ListTaskUpdatesToolIn, _list_task_updates)
_register("add_comment", "Thêm bình luận vào 1 task.", AddCommentToolIn, _add_comment)
_register("list_comments", "Liệt kê bình luận của 1 task.", ListCommentsToolIn, _list_comments)
_register("create_skill", "Tạo skill mới kèm nội dung version 1 (chỉ CEO).",
          SkillCreateIn, _create_skill)
_register("add_skill_version", "Thêm version nội dung mới cho skill (chỉ CEO).",
          AddSkillVersionToolIn, _add_skill_version)
_register("grant_skill", "Cấp quyền dùng skill cho 1 người (chỉ CEO).",
          GrantSkillToolIn, _grant_skill)
_register("list_skills", "Liệt kê skill actor được thấy/được cấp.", NoArgsIn, _list_skills)
_register("use_skill", "Dùng skill: lấy nội dung version mới nhất + trạng thái task sống.",
          UseSkillToolIn, _use_skill)
_register("list_skill_grants", "Xem những ai đang được cấp quyền dùng 1 skill (chỉ CEO).",
          ListSkillGrantsToolIn, _list_skill_grants)
_register("revoke_skill_grant", "Thu hồi quyền dùng skill của 1 người (chỉ CEO).",
          RevokeSkillGrantToolIn, _revoke_skill_grant)


class CreateEmployeeToolIn(BaseModel):
    email: EmailStr
    full_name: str
    role: Role
    manager_id: uuid.UUID | None = None


class LockUserToolIn(BaseModel):
    target_id: uuid.UUID


class UnlockUserToolIn(BaseModel):
    target_id: uuid.UUID


async def _list_users(db, actor, body: NoArgsIn) -> dict:
    """Danh bạ công ty — mọi vai trò thấy đủ thành viên workspace mình (để lấy
    user_id khi giao việc/gửi email/khóa...). Quyền HÀNH ĐỘNG lên từng người vẫn
    kiểm ở service layer của tool tương ứng; đây chỉ là thông tin danh bạ."""
    rows = await db.execute(
        select(User).where(User.workspace_id == actor.workspace_id)
        .order_by(User.full_name.asc())
    )
    return {"users": [{"id": str(u.id), "full_name": u.full_name, "email": u.email,
                       "role": u.role.value} for u in rows.scalars()]}


async def _create_employee(db, actor, body: CreateEmployeeToolIn) -> dict:
    user, code, expires_at = await auth_service.create_employee(
        db, actor=actor, email=body.email, full_name=body.full_name,
        role=body.role.value, manager_id=body.manager_id)
    return {"user_id": str(user.id), "email": user.email, "full_name": user.full_name,
           "role": user.role.value, "activation_code": code,
           "expires_at": expires_at.isoformat(),
           "note": f"Đưa mã kích hoạt '{code}' cho {user.full_name} (nói trực tiếp, nhắn "
                   "Zalo...) — họ mở app, chọn 'Kích hoạt tài khoản', nhập mã này + tự đặt "
                   "mật khẩu. Không cần họ tự đăng ký gì thêm."}


async def _lock_user(db, actor, body: LockUserToolIn) -> dict:
    await auth_service.lock_user(db, actor, body.target_id)
    return {"user_id": str(body.target_id), "locked": True}


async def _unlock_user(db, actor, body: UnlockUserToolIn) -> dict:
    await auth_service.unlock_user(db, actor, body.target_id)
    return {"user_id": str(body.target_id), "locked": False}


class OffboardUserToolIn(BaseModel):
    user_id: uuid.UUID
    successor_id: uuid.UUID | None = None


async def _offboard_user(db, actor, body: OffboardUserToolIn) -> dict:
    return await auth_service.offboard_user(db, actor, body.user_id, body.successor_id)


class ChangeUserRoleToolIn(BaseModel):
    user_id: uuid.UUID
    new_role: Role | None = None
    new_manager_id: uuid.UUID | None = None
    successor_id: uuid.UUID | None = None


async def _change_user_role(db, actor, body: ChangeUserRoleToolIn) -> dict:
    return await auth_service.change_role(db, actor, body.user_id, new_role=body.new_role,
                                          new_manager_id=body.new_manager_id,
                                          successor_id=body.successor_id)


_register("list_users", "Danh bạ công ty: liệt kê thành viên (id, tên, email, vai trò). "
          "Dùng để tra user_id theo tên trước khi giao task, gửi email, khóa/mở tài khoản "
          "— đừng bao giờ hỏi người dùng user_id.", NoArgsIn, _list_users)
_register("create_employee", "Tạo tài khoản nhân viên/quản lý MỚI trực tiếp (chỉ CEO) — "
          "KHÔNG cần người đó tự đăng ký/chấp nhận lời mời gì cả. Trả về activation_code — "
          "CEO tự đưa mã này cho người được thêm (nói trực tiếp, nhắn Zalo...) để họ mở app, "
          "chọn 'Kích hoạt tài khoản', nhập mã + tự đặt mật khẩu. Dùng khi nghe 'thêm nhân "
          "viên X', 'mời Y vào làm quản lý', 'nhận Z làm nhân viên của A'.",
          CreateEmployeeToolIn, _create_employee)
_register("lock_user", "Khóa tài khoản 1 người — đăng xuất khỏi mọi thiết bị "
          "(chỉ CEO, hành động nhạy cảm - hệ thống TỰ hiện bước xác nhận khi gọi tool, cứ gọi ngay đừng hỏi trước).", LockUserToolIn, _lock_user,
          sensitive=True)
_register("unlock_user", "Mở khóa tài khoản 1 người (chỉ CEO, hành động nhạy cảm - hệ thống TỰ hiện bước xác nhận khi gọi tool, cứ gọi ngay đừng hỏi trước).",
          UnlockUserToolIn, _unlock_user, sensitive=True)
_register("offboard_user",
          "Cho 1 người nghỉ việc — khóa tài khoản (đăng xuất mọi thiết bị) và bàn giao toàn bộ "
          "task/project/nhân viên báo cáo trực tiếp (nếu có) cho 1 người kế thừa (chỉ CEO, hành "
          "động nhạy cảm - hệ thống TỰ hiện bước xác nhận khi gọi tool, cứ gọi ngay đừng hỏi trước).",
          OffboardUserToolIn, _offboard_user, sensitive=True)
_register("change_user_role",
          "Đổi vai trò (employee/manager/ceo) và/hoặc đổi người quản lý trực tiếp của 1 người "
          "ĐANG làm việc (không khóa tài khoản, không đụng task đang được giao của họ). Nếu đổi "
          "khỏi vai trò manager mà người đó đang có nhân viên báo cáo hoặc đang sở hữu project, "
          "PHẢI cung cấp successor_id để bàn giao. Chỉ CEO gọi được; đổi liên quan tới vai trò CEO "
          "(thăng ai đó thành CEO, hoặc đổi role của 1 CEO khác) chỉ root CEO gọi được — hành động "
          "nhạy cảm, hệ thống TỰ hiện bước xác nhận khi gọi tool, cứ gọi ngay đừng hỏi trước.",
          ChangeUserRoleToolIn, _change_user_role, sensitive=True)


class GenerateReportToolIn(BaseModel):
    project_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    date_from: date | None = None
    date_to: date | None = None
    status: TaskStatus | None = None
    columns: list[str] | None = Field(
        None, description="Cột tùy chọn, thứ tự tùy ý, thiếu = mặc định tất cả. "
        "Giá trị hợp lệ: title, project, status, percent, assignees, latest_update, deadline.")


async def _generate_report(db, actor, body: GenerateReportToolIn) -> dict:
    return await report_service.generate_report(db, actor, **body.model_dump())


_register("generate_report",
          "Tạo báo cáo Excel tổng hợp task, filter tùy chọn theo project/người/khoảng "
          "thời gian/trạng thái, cột tùy biến (chỉ CEO). Trả về report_id + tóm tắt "
          "số liệu; file tải qua ứng dụng.", GenerateReportToolIn, _generate_report)


async def _list_reports(db, actor, body: NoArgsIn) -> dict:
    reports = await report_service.list_reports(db, actor)
    result = {"reports": [
        {"id": str(r.id), "kind": r.kind, "filters": r.filters, "summary": r.summary,
         "created_at": r.created_at.isoformat()}
        for r in reports
    ]}
    if not reports:
        result["note"] = "Chưa có báo cáo Excel nào được tạo trước đây."
    return result


_register("list_reports", "Liệt kê các báo cáo Excel đã tạo trước đây trong công ty "
          "(chỉ CEO) — mỗi báo cáo kèm tóm tắt số liệu, tải file qua ứng dụng.",
          NoArgsIn, _list_reports)


class CreateReportScheduleToolIn(BaseModel):
    weekday: int | None = None
    hour: int
    minute: int = 0
    project_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    status: TaskStatus | None = None
    recipient_id: uuid.UUID | None = None


class DeleteReportScheduleToolIn(BaseModel):
    schedule_id: uuid.UUID


def _schedule_out(s) -> dict:
    return {"id": str(s.id), "weekday": s.weekday, "hour": s.hour, "minute": s.minute,
           "project_id": str(s.project_id) if s.project_id else None,
           "assignee_id": str(s.assignee_id) if s.assignee_id else None,
           "status": s.status.value if s.status else None,
           "recipient_id": str(s.recipient_id), "active": s.active,
           "next_run_at": s.next_run_at.isoformat()}


async def _create_report_schedule(db, actor, body: CreateReportScheduleToolIn) -> dict:
    sched = await report_schedule_service.create_schedule(db, actor, **body.model_dump())
    return _schedule_out(sched)


async def _list_report_schedules(db, actor, body: NoArgsIn) -> dict:
    rows = await report_schedule_service.list_schedules(db, actor)
    result = {"schedules": [_schedule_out(s) for s in rows]}
    if not rows:
        result["note"] = "Chưa có lịch báo cáo định kỳ nào."
    return result


async def _delete_report_schedule(db, actor, body: DeleteReportScheduleToolIn) -> dict:
    await report_schedule_service.delete_schedule(db, actor, body.schedule_id)
    return {"schedule_id": str(body.schedule_id), "deleted": True}


_register("create_report_schedule",
          "Đặt lịch tự động gửi báo cáo tiến độ định kỳ (chỉ CEO, gói Advanced). "
          "Tự tính weekday từ ngôn ngữ tự nhiên: 0=Thứ Hai...6=Chủ Nhật, để trống "
          "(null) nếu là hàng ngày. Giờ theo GIỜ VIỆT NAM (UTC+7). VD 'mỗi sáng thứ 2 lúc 8h' → "
          "weekday=0, hour=8, minute=0.", CreateReportScheduleToolIn,
          _create_report_schedule)
_register("list_report_schedules", "Liệt kê lịch báo cáo định kỳ đang có (chỉ CEO).",
          NoArgsIn, _list_report_schedules)
_register("delete_report_schedule", "Hủy 1 lịch báo cáo định kỳ theo id (chỉ CEO).",
          DeleteReportScheduleToolIn, _delete_report_schedule)


class ListAuditEventsToolIn(BaseModel):
    date_from: date | None = None
    date_to: date | None = None


async def _list_audit_events(db, actor, body: ListAuditEventsToolIn) -> dict:
    events = await audit_service.list_audit_events(db, actor, date_from=body.date_from,
                                                   date_to=body.date_to)
    result = {"events": events}
    if not events:
        result["note"] = "Không có nhật ký thay đổi nào khớp khoảng thời gian này."
    return result


_register("list_audit_events", "Xem nhật ký thay đổi công ty: cập nhật task, đăng nhập, "
          "khóa/mở/nghỉ việc/đổi vai trò tài khoản, sửa instruction/skill (chỉ CEO, tối đa "
          "200 dòng gần nhất).", ListAuditEventsToolIn, _list_audit_events)


class SendEmailToolIn(BaseModel):
    recipient_id: uuid.UUID
    subject: str
    body: str
    task_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None


async def _send_email(db, actor, body: SendEmailToolIn) -> dict:
    email = await email_service.send_email(db, actor, body.recipient_id, body.subject,
                                           body.body, task_id=body.task_id,
                                           project_id=body.project_id)
    return {"id": str(email.id), "subject": email.subject, "sent": True}


class CreateDirectiveToolIn(BaseModel):
    recipient_id: uuid.UUID
    task_id: uuid.UUID | None = None
    verbatim_text: str
    structured_summary: str = ""
    deadline: datetime | None = None


async def _create_directive(db, actor, body: CreateDirectiveToolIn) -> dict:
    return await directive_service.create_directive(
        db, actor, recipient_id=body.recipient_id, task_id=body.task_id,
        verbatim_text=body.verbatim_text, structured_summary=body.structured_summary,
        deadline=body.deadline)


_register("create_directive", "Giao việc CHÍNH THỨC cho 1 người — khác update_task/assign_task "
          "ở chỗ tạo ra 1 'directive' có trạng thái riêng (sent/acked/...), gửi thông báo + "
          "email nội bộ, và người nhận PHẢI xác nhận đã nhận việc. Dùng khi câu nói mang tính "
          "CHỈ THỊ rõ ràng (vd 'bảo X làm Y', 'giao Y cho X') — không dùng cho việc cập nhật/"
          "sửa task thông thường (dùng update_task/assign_task cho việc đó). CEO giao được cho "
          "bất kỳ ai; manager chỉ giao được cho nhân viên dưới quyền trực tiếp của mình. Gọi "
          "bên trong propose_actions cùng update_task nếu câu nói vừa đổi deadline vừa giao "
          "việc.", CreateDirectiveToolIn, _create_directive)


class GetDirectiveStatusToolIn(BaseModel):
    pass


async def _get_directive_status(db, actor, body: GetDirectiveStatusToolIn) -> dict:
    return await directive_service.get_directive_status(db, actor)


_register("get_directive_status", "Xem tình trạng các directive (việc đã giao chính thức) "
          "trong phạm vi actor được thấy — dùng khi hỏi 'tuần này tôi giao gì', 'ai chưa xác "
          "nhận', 'Duy còn nợ tôi mấy việc'. Trả danh sách kèm trạng thái, không tự tính toán "
          "— đọc thẳng kết quả.", GetDirectiveStatusToolIn, _get_directive_status)


_register("send_email", "Gửi email cho 1 người trong công ty theo ma trận tương tác "
          "(nhân viên không gửi được cho nhân viên khác). Gắn task_id/project_id nếu "
          "nội dung mail liên quan tới 1 task/project cụ thể. Hành động nhạy cảm - hệ "
          "thống TỰ hiện bước xác nhận khi gọi tool, cứ gọi ngay đừng hỏi trước.",
          SendEmailToolIn, _send_email, sensitive=True)


class CreateInstructionToolIn(BaseModel):
    title: str
    content: str


class UpdateInstructionToolIn(BaseModel):
    instruction_id: uuid.UUID
    content: str


class DeleteInstructionToolIn(BaseModel):
    instruction_id: uuid.UUID


async def _create_instruction(db, actor, body: CreateInstructionToolIn) -> dict:
    ins = await instruction_service.create_instruction(db, actor, body.title, body.content)
    return {"id": str(ins.id), "title": ins.title, "version": ins.version}


async def _update_instruction(db, actor, body: UpdateInstructionToolIn) -> dict:
    version = await instruction_service.update_instruction(db, actor, body.instruction_id,
                                                           body.content)
    return {"id": str(body.instruction_id), "version": version}


async def _list_instructions(db, actor, body: NoArgsIn) -> dict:
    items = await instruction_service.list_instructions(db, actor)
    result = {"instructions": [{"id": str(i["id"]), "title": i["title"],
                                "version": i["version"], "content": i["content"]}
                               for i in items]}
    if not items:
        result["note"] = "Công ty chưa có instruction nào."
    return result


async def _delete_instruction(db, actor, body: DeleteInstructionToolIn) -> dict:
    await instruction_service.delete_instruction(db, actor, body.instruction_id)
    return {"id": str(body.instruction_id), "deleted": True}


_register("create_instruction", "Tạo instruction — chỉ dẫn định hình cách AI hành xử "
          "trong công ty, AI nạp lại ngay (chỉ CEO).", CreateInstructionToolIn,
          _create_instruction)
_register("update_instruction", "Cập nhật nội dung instruction, tăng phiên bản, AI nạp "
          "lại ngay (chỉ CEO).", UpdateInstructionToolIn, _update_instruction)
_register("list_instructions", "Liệt kê instruction của công ty kèm nội dung mới nhất "
          "(chỉ CEO).", NoArgsIn, _list_instructions)
_register("delete_instruction", "Xóa/thu hồi 1 instruction (chỉ CEO, hành động nhạy cảm - "
          "hệ thống TỰ hiện bước xác nhận khi gọi tool, cứ gọi ngay đừng hỏi trước).",
          DeleteInstructionToolIn, _delete_instruction, sensitive=True)


class CreateNoteToolIn(BaseModel):
    content: str
    tags: list[str] = []
    note_date: date | None = None
    task_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None


class ListNotesToolIn(BaseModel):
    on_date: date | None = None
    tag: str | None = None


def _note_out(n) -> dict:
    return {"id": str(n.id), "content": n.content, "tags": n.tags or [],
            "note_date": n.note_date.isoformat(),
            "task_id": str(n.task_id) if n.task_id else None,
            "project_id": str(n.project_id) if n.project_id else None}


async def _create_note(db, actor, body: CreateNoteToolIn) -> dict:
    note = await note_service.create_note(db, actor, **body.model_dump())
    return _note_out(note)


async def _list_notes(db, actor, body: ListNotesToolIn) -> dict:
    notes = await note_service.list_notes(db, actor, on_date=body.on_date, tag=body.tag)
    result = {"notes": [_note_out(n) for n in notes]}
    if not notes:
        result["note"] = "Không có ghi chú nào khớp bộ lọc này."
    return result


class GetPortalReportToolIn(BaseModel):
    report_id: str


async def _list_portal_reports(db, actor, body: NoArgsIn) -> dict:
    reports = await portal_service.list_reports(db, actor)
    result = {"reports": [{"id": r["id"], "title": r["title"], "period": r["period"],
                           "summary": r["summary"]} for r in reports]}
    if not reports:
        result["note"] = "Cổng CEO chưa có báo cáo nào."
    return result


async def _get_portal_report(db, actor, body: GetPortalReportToolIn) -> dict:
    return dict(await portal_service.get_report(db, actor, body.report_id))


_register("list_portal_reports", "Liệt kê báo cáo từ cổng CEO ceo.9learning.edu.vn "
          "(chỉ CEO, gói Advanced).", NoArgsIn, _list_portal_reports)
_register("get_portal_report", "Đọc chi tiết 1 báo cáo từ cổng CEO để tóm tắt/đối chiếu "
          "với tiến độ task (chỉ CEO, gói Advanced).", GetPortalReportToolIn,
          _get_portal_report)


async def _get_today_dashboard(db, actor, body: NoArgsIn) -> dict:
    return await dashboard_service.today_dashboard(db, actor)


class ListVoiceNotesToolIn(BaseModel):
    tag: str | None = None
    on_date: date | None = None


class GetVoiceNoteToolIn(BaseModel):
    voice_note_id: uuid.UUID


async def _list_voice_notes(db, actor, body: ListVoiceNotesToolIn) -> dict:
    notes = await voice_service.list_voice_notes(db, actor, tag=body.tag,
                                                 on_date=body.on_date)
    result = {"voice_notes": notes}
    if not notes:
        result["note"] = "Không có ghi âm nào khớp bộ lọc này."
    return result


async def _get_voice_note(db, actor, body: GetVoiceNoteToolIn) -> dict:
    return await voice_service.get_voice_note(db, actor, body.voice_note_id)


_register("list_voice_notes", "Liệt kê ghi âm của chính người dùng (lọc theo tag/ngày), "
          "kèm transcript.", ListVoiceNotesToolIn, _list_voice_notes)
_register("get_voice_note", "Đọc 1 ghi âm (transcript + metadata) — dùng để biến ghi âm "
          "thành task/cập nhật theo yêu cầu.", GetVoiceNoteToolIn, _get_voice_note)


class ListTaskAttachmentsToolIn(BaseModel):
    task_id: uuid.UUID


async def _list_task_attachments(db, actor, body: ListTaskAttachmentsToolIn) -> dict:
    attachments = await attachment_service.list_attachments(db, actor, body.task_id)
    result = {"attachments": attachments}
    if not attachments:
        result["note"] = "Task này chưa có tài liệu đính kèm nào."
    return result


_register("list_task_attachments", "Liệt kê tài liệu đính kèm của 1 task (tên file, dung "
          "lượng, người đính kèm, thời gian).", ListTaskAttachmentsToolIn,
          _list_task_attachments)


_register("get_today_dashboard", "Tổng hợp 'Hôm nay' theo phạm vi quyền của người dùng: "
          "task đến hạn hôm nay / quá hạn / đang làm, cập nhật 24h qua, note hôm nay, "
          "counters.", NoArgsIn, _get_today_dashboard)
_register("create_note", "Tạo ghi chú cá nhân (text), gắn tag/ngày/task/project tùy chọn. "
          "Note là riêng tư của người tạo.", CreateNoteToolIn, _create_note)
_register("list_notes", "Liệt kê ghi chú cá nhân của chính người dùng, lọc theo ngày "
          "(on_date) hoặc tag.", ListNotesToolIn, _list_notes)


class GetProjectHealthToolIn(BaseModel):
    project_id: uuid.UUID


async def _get_project_health(db, actor, body: GetProjectHealthToolIn) -> dict:
    return await analytics_service.get_project_health(db, actor, body.project_id)


class GetProgressStatsToolIn(BaseModel):
    period: str = "week"
    project_id: uuid.UUID | None = None


async def _get_progress_stats(db, actor, body: GetProgressStatsToolIn) -> dict:
    return await analytics_service.get_progress_stats(
        db, actor, period=body.period, project_id=body.project_id)


_register("get_project_health", "Soi sâu 1 project cụ thể: task bị blocked (kèm số ngày bị "
          "chặn), task quá hạn (kèm số ngày trễ), task im lặng >7 ngày không cập nhật, tiến "
          "độ trung bình, và 1 mức 'risk' tổng quát (high/medium/low). Dùng khi user hỏi "
          "'project X đang ổn không', 'project nào đang có rủi ro'. Khác get_today_dashboard "
          "(tổng quan toàn phạm vi) ở chỗ tool này đào sâu MỘT project.", GetProjectHealthToolIn,
          _get_project_health)
_register("get_progress_stats", "So sánh tiến độ kỳ này với kỳ trước (period='week' hoặc "
          "'month'): số task hoàn thành, số task tạo mới, số task đang quá hạn — kèm chênh "
          "lệch (change) so với kỳ trước liền kề. Truyền project_id để giới hạn 1 project, "
          "bỏ trống để tính theo toàn phạm vi actor được thấy. Dùng khi user hỏi 'tuần này "
          "làm được nhiêu so với tuần trước', 'tháng này tiến độ sao'.", GetProgressStatsToolIn,
          _get_progress_stats)


class SearchToolIn(BaseModel):
    q: str = Field(min_length=1)


async def _search(db, actor, body: SearchToolIn) -> dict:
    result = await search_service.search(db, actor, body.q)
    if not any(result.values()):
        result["note"] = f"Không tìm thấy gì khớp '{body.q}' trong phạm vi bạn thấy."
    return result


_register("search", "Tìm kiếm xuyên suốt theo từ khóa: task, note, ghi âm, người, skill "
          "(chỉ trong phạm vi actor được thấy). Dùng khi user hỏi 'tìm ... liên quan tới X'.",
          SearchToolIn, _search)


class SemanticSearchToolIn(BaseModel):
    query: str = Field(min_length=1)
    source_types: list[Literal["note", "task_update", "comment", "chat_message",
                               "voice_transcript", "skill"]] | None = Field(
        None, description="Giới hạn loại nguồn, để trống = tìm cả 6 loại.")


async def _semantic_search(db, actor, body: SemanticSearchToolIn) -> dict:
    results = await embedding_service.semantic_search(
        db, actor, body.query, source_types=body.source_types)
    out = {"results": results}
    if not results:
        out["note"] = f"Không tìm thấy gì đủ liên quan tới nghĩa của '{body.query}'."
    return out


class ForgetMemoryToolIn(BaseModel):
    memory_id: uuid.UUID


async def _list_memories(db, actor, body: NoArgsIn) -> dict:
    memories = await distiller_service.list_memories(db, actor)
    result = {"memories": [
        {"id": str(m["id"]), "scope": m["scope"], "content": m["content"],
         "source": m["source"], "created_at": m["created_at"].isoformat()}
        for m in memories
    ]}
    if not memories:
        result["note"] = "Chưa có ghi nhớ dài hạn nào được chưng cất."
    return result


async def _forget_memory(db, actor, body: ForgetMemoryToolIn) -> dict:
    await distiller_service.forget_memory(db, actor, body.memory_id)
    return {"memory_id": str(body.memory_id), "forgotten": True}


_register("list_memories", "Xem các 'ghi nhớ dài hạn' AI tự chưng cất mỗi đêm từ hoạt động "
          "công ty (quyết định đã chốt, vấn đề lặp lại...), chỉ CEO xem được. Dùng khi CEO "
          "hỏi 'AI đang nhớ gì về công ty', hoặc trước khi xóa 1 ghi nhớ sai.", NoArgsIn,
          _list_memories)
_register("forget_memory", "Xóa (thu hồi) 1 ghi nhớ dài hạn theo id — dùng khi ghi nhớ đó sai "
          "hoặc lỗi thời (chỉ CEO).", ForgetMemoryToolIn, _forget_memory)


_register("semantic_search",
          "Tìm THEO NGỮ NGHĨA (không cần trùng chữ) trong ghi chú, cập nhật tiến độ, "
          "bình luận task, lịch sử chat, transcript ghi âm (của CHÍNH actor), và nội dung "
          "skill (theo đúng quyền — CEO thấy hết, người khác chỉ skill được cấp) — dùng khi "
          "cần nhớ lại điều đã nói/ghi trước đây mà 'Trạng thái công ty' hoặc lịch sử hội "
          "thoại hiện tại không có (vd 'tuần trước tôi dặn gì về hợp đồng X', 'trước đây có "
          "ghi chú gì về khách hàng Y không', 'skill nào nói về quy trình Z'). Khác search "
          "(khớp từ khóa đúng chuỗi con) ở chỗ tìm được cả khi câu hỏi diễn đạt khác chữ với "
          "nội dung gốc.", SemanticSearchToolIn, _semantic_search)


class ListNotificationsToolIn(BaseModel):
    unread_only: bool = False


async def _list_notifications(db, actor, body: ListNotificationsToolIn) -> dict:
    notifs = await notification_service.list_notifications(db, actor,
                                                            unread_only=body.unread_only)
    result = {"notifications": [
        {"id": str(n.id), "type": n.type, "payload": n.payload,
         "read_at": n.read_at.isoformat() if n.read_at else None,
         "created_at": n.created_at.isoformat()}
        for n in notifs
    ]}
    if not notifs:
        result["note"] = "Không có thông báo nào" + (" chưa đọc." if body.unread_only else ".")
    return result


_register("list_notifications", "Xem thông báo của chính actor (task được giao, cập nhật "
          "tiến độ, đổi vai trò, yêu cầu mở khóa...). unread_only=true để chỉ xem chưa đọc.",
          ListNotificationsToolIn, _list_notifications)


async def _get_notification_preferences(db, actor, body: NoArgsIn) -> dict:
    return await notification_service.get_preferences(actor)


_register("get_notification_preferences", "Xem loại thông báo nào actor đã tự tắt "
          "(mặc định mọi loại đều bật).", NoArgsIn, _get_notification_preferences)


class SetNotificationPreferenceToolIn(BaseModel):
    type: str = Field(description="vd: task_assigned, task_update, scheduled_report...")
    enabled: bool


async def _set_notification_preference(db, actor, body: SetNotificationPreferenceToolIn) -> dict:
    return await notification_service.set_preference(db, actor, body.type, body.enabled)


_register("set_notification_preference", "Bật/tắt 1 loại thông báo cho chính actor "
          "(vd 'tắt thông báo cập nhật task' -> type=task_update, enabled=false).",
          SetNotificationPreferenceToolIn, _set_notification_preference)


class ResolvePersonToolIn(BaseModel):
    query: str = Field(min_length=1)


async def _resolve_person(db, actor, body: ResolvePersonToolIn) -> dict:
    return await resolver_service.resolve_person(db, actor, body.query)


_register("resolve_person", "Tìm người theo tên/biệt danh, chịu được không dấu/viết tắt "
          "(vd 'duy' khớp 'Duy Phạm'). Trả match duy nhất, danh sách ứng viên nếu nhập "
          "nhằng (>1 người tên gần giống), hoặc not_found. TUYỆT ĐỐI không đoán khi có "
          ">1 ứng viên — hỏi lại người dùng đúng 1 câu kèm danh sách cụ thể. Ưu tiên khớp "
          "từ danh bạ trong system prompt trước, tool này là lớp dự phòng cho ca khó "
          "(trùng tên, tên lạ).", ResolvePersonToolIn, _resolve_person)


class ResolveTaskToolIn(BaseModel):
    query: str = ""
    assignee_id: uuid.UUID | None = None


async def _resolve_task(db, actor, body: ResolveTaskToolIn) -> dict:
    return await resolver_service.resolve_task(db, actor, body.query, body.assignee_id)


_register("resolve_task", "Tìm task theo tiêu đề/mô tả và/hoặc theo người phụ trách "
          "(assignee_id) — dùng khi câu lệnh nhắc tên người nhưng không nêu rõ task nào "
          "(vd 'Duy có mấy task' -> assignee_id=id của Duy, query để trống). Chịu được "
          "không dấu/viết tắt trong query. Trả match duy nhất, danh sách ứng viên nếu "
          "nhập nhằng, hoặc not_found. TUYỆT ĐỐI không đoán khi có >1 ứng viên — hỏi lại "
          "đúng 1 câu kèm danh sách cụ thể.", ResolveTaskToolIn, _resolve_task)


class ProposedActionIn(BaseModel):
    tool_name: str
    tool_input: dict = {}
    display_text: str


class ProposeActionsToolIn(BaseModel):
    actions: list[ProposedActionIn] = Field(min_length=1)
    reasoning: str = ""


def validate_proposal_actions(actions: list[dict]) -> str | None:
    """None nếu hợp lệ; nếu không, trả lý do (cho model đọc lại và tự sửa lượt sau)."""
    if not actions:
        return "actions rỗng — propose_actions cần ít nhất 1 hành động."
    for a in actions:
        name = a.get("tool_name")
        if name not in TOOLS:
            return f"tool_name '{name}' không tồn tại — gọi lại với tên tool đúng."
        if name == "propose_actions" or name in SENSITIVE_TOOLS:
            return (f"tool_name '{name}' không được đưa vào propose_actions (nhạy cảm/"
                   "chính nó phải xác nhận riêng) — gọi tool đó trực tiếp thay vì lồng vào đây.")
    return None


async def _propose_actions_noop(db, actor, body: ProposeActionsToolIn) -> dict:
    # KHONG BAO GIO duoc goi that qua call_tool — loop.py chan propose_actions truoc
    # khi toi day (giong het cach sensitive tool khong bao gio chay luc phat hien).
    # Handler ton tai vi ToolSpec yeu cau 1 callable; day la safety-net neu lot qua.
    return {"error": "tool_failed", "hint": "propose_actions không được gọi trực tiếp qua call_tool."}


_register("propose_actions",
    "Trình bản nháp 1+ hành động cho người dùng duyệt trước khi thực thi. "
    "BẮT BUỘC dùng khi: (a) phải SUY LUẬN đối tượng (đoán task/người/deadline từ "
    "ngữ cảnh thay vì user nói tường minh), (b) hành động khó đảo ngược, "
    "(c) gộp nhiều hành động một lượt. Gọi NGAY, hệ thống tự hiện thẻ xác nhận — "
    "đừng tự hỏi xác nhận bằng lời. Mỗi action cần display_text là 1 câu tiếng Việt "
    "người đọc hiểu ngay hành động đó làm gì (vd 'Cập nhật task X lên 80%').",
    ProposeActionsToolIn, _propose_actions_noop)


# Phân nhóm tool cho Router động (Phase 4, §6.4/§8 spec) — CHỈ dữ liệu, CHƯA wiring
# lọc vào _tool_specs_for_api()/loop.py (quyết định thiết kế #3 trong plan Phase 2:
# Router chưa xây, wiring sớm hoặc vô nghĩa hoặc âm thầm bỏ sót tool model cần).
TOOL_GROUPS: dict[str, frozenset[str]] = {
    "core": frozenset({
        "get_task", "search", "semantic_search", "resolve_person", "resolve_task",
        "propose_actions",
    }),
    "work": frozenset({
        "create_project", "update_project", "list_projects",
        "create_task", "update_task", "list_tasks", "assign_task", "unassign_task",
        "delete_task", "delete_project", "add_task_update", "list_task_updates",
        "add_comment", "list_comments", "send_email", "list_task_attachments",
        "create_directive",
    }),
    "admin": frozenset({
        "list_users", "create_employee", "lock_user", "unlock_user",
        "offboard_user", "change_user_role", "list_audit_events", "forget_memory",
    }),
    "reporting": frozenset({
        "generate_report", "list_reports", "create_report_schedule",
        "list_report_schedules", "delete_report_schedule",
        "list_portal_reports", "get_portal_report",
    }),
    "skill_instruction": frozenset({
        "create_skill", "add_skill_version", "grant_skill", "list_skills", "use_skill",
        "list_skill_grants", "revoke_skill_grant",
        "create_instruction", "update_instruction", "list_instructions", "delete_instruction",
    }),
    "personal": frozenset({
        "list_voice_notes", "get_voice_note", "create_note", "list_notes",
        "list_notifications", "get_notification_preferences", "set_notification_preference",
    }),
    "insight": frozenset({
        "get_today_dashboard", "get_directive_status",
        "get_project_health", "get_progress_stats", "list_memories",
    }),
}


SENSITIVE_TOOLS: frozenset[str] = frozenset(
    name for name, spec in TOOLS.items() if spec.sensitive
)

# Tool làm THAY ĐỔI dữ liệu nuôi snapshot (project/task/người) — agent loop
# invalidate cache snapshot ngay sau khi chạy để lượt sau AI thấy việc mình vừa
# làm. Ghi từ REST của FE dựa vào TTL (spec §5.2, deviation đã chốt trong plan).
SNAPSHOT_WRITE_TOOLS: frozenset[str] = frozenset({
    "create_project", "update_project", "delete_project",
    "create_task", "update_task", "delete_task",
    "assign_task", "unassign_task", "add_task_update",
    "offboard_user", "change_user_role", "create_directive", "create_employee",
})
