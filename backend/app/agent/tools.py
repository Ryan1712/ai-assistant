from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.schemas import ProjectCreateIn, ProjectPatchIn, TaskCreateIn, TaskPatchIn
from app.services import work_service


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


async def call_tool(db: AsyncSession, actor: User, tool_name: str, tool_input: dict) -> dict:
    """Gọi 1 tool theo tên; lỗi service (HTTPException) bọc thành tool_result lỗi, không raise ra ngoài."""
    spec = TOOLS[tool_name]
    try:
        parsed = spec.input_model(**tool_input)
    except Exception as exc:
        return {"error": "invalid_input", "message": f"Dữ liệu đầu vào không hợp lệ: {exc}"}
    try:
        return await spec.handler(db, actor, parsed)
    except HTTPException as exc:
        label = _ERROR_LABELS.get(exc.status_code, "error")
        message = _ERROR_MESSAGES.get(exc.status_code, str(exc.detail))
        return {"error": label, "message": message}


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


async def _create_project(db, actor, body: ProjectCreateIn) -> dict:
    project = await work_service.create_project(db, actor, **body.model_dump())
    return {"id": str(project.id), "name": project.name, "status": project.status}


async def _update_project(db, actor, body: UpdateProjectToolIn) -> dict:
    patch = body.model_dump(exclude={"project_id"}, exclude_unset=True)
    project = await work_service.update_project(db, actor, body.project_id, patch)
    return {"id": str(project.id), "name": project.name, "status": project.status}


async def _list_projects(db, actor, body: NoArgsIn) -> dict:
    projects = await work_service.list_projects(db, actor)
    return {"projects": [{"id": str(p.id), "name": p.name, "status": p.status} for p in projects]}


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
    return {"tasks": [{"id": str(t["id"]), "title": t["title"], "status": t["status"].value,
                       "percent": t["percent"]} for t in tasks]}


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
