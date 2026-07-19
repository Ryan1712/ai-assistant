import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import ProjectCreateIn, ProjectOut, ProjectPatchIn
from app.services import work_service

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(body: ProjectCreateIn,
                         actor: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    return await work_service.create_project(db, actor, **body.model_dump())


@router.get("", response_model=list[ProjectOut])
async def list_projects(actor: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    return await work_service.list_projects(db, actor)


@router.patch("/{project_id}", response_model=ProjectOut)
async def patch_project(project_id: uuid.UUID, body: ProjectPatchIn,
                        actor: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    return await work_service.update_project(
        db, actor, project_id, body.model_dump(exclude_unset=True))


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: uuid.UUID, actor: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    await work_service.delete_project(db, actor, project_id)
