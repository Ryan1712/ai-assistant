import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import AssigneeIn, TaskCreateIn, TaskOut, TaskPatchIn
from app.services import work_service

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(body: TaskCreateIn, actor: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    return await work_service.create_task(db, actor, **body.model_dump())


@router.get("", response_model=list[TaskOut])
async def list_tasks(actor: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    return await work_service.list_tasks(db, actor)


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: uuid.UUID, actor: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db)):
    return await work_service.get_task(db, actor, task_id)


@router.patch("/{task_id}", response_model=TaskOut)
async def patch_task(task_id: uuid.UUID, body: TaskPatchIn,
                     actor: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    return await work_service.update_task(
        db, actor, task_id, body.model_dump(exclude_unset=True))


@router.post("/{task_id}/assignees")
async def assign(task_id: uuid.UUID, body: AssigneeIn,
                 actor: User = Depends(get_current_user),
                 db: AsyncSession = Depends(get_db)):
    created = await work_service.assign_task(db, actor, task_id, body.user_id)
    return Response(status_code=201 if created else 200)


@router.delete("/{task_id}/assignees/{user_id}", status_code=204)
async def unassign(task_id: uuid.UUID, user_id: uuid.UUID,
                   actor: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db)):
    await work_service.unassign_task(db, actor, task_id, user_id)
    return Response(status_code=204)
