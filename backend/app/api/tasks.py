import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import (
    AssigneeIn,
    CommentCreateIn,
    CommentOut,
    TaskCreateIn,
    TaskOut,
    TaskPatchIn,
    TaskUpdateCreateIn,
    TaskUpdateOut,
)
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


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: uuid.UUID, actor: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    await work_service.delete_task(db, actor, task_id)


@router.post("/{task_id}/assignees", responses={201: {"description": "Assigned"}})
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


@router.post("/{task_id}/updates", response_model=TaskUpdateOut, status_code=201)
async def add_update(task_id: uuid.UUID, body: TaskUpdateCreateIn,
                     actor: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    return await work_service.add_task_update(db, actor, task_id, **body.model_dump())


@router.get("/{task_id}/updates", response_model=list[TaskUpdateOut])
async def list_updates(task_id: uuid.UUID, actor: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    return await work_service.list_task_updates(db, actor, task_id)


@router.post("/{task_id}/comments", response_model=CommentOut, status_code=201)
async def add_comment(task_id: uuid.UUID, body: CommentCreateIn,
                      actor: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    return await work_service.add_comment(db, actor, task_id, body.content)


@router.get("/{task_id}/comments", response_model=list[CommentOut])
async def list_comments(task_id: uuid.UUID, actor: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    return await work_service.list_comments(db, actor, task_id)
