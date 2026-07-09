import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import SkillCreateIn, SkillGrantIn, SkillOut, SkillVersionIn, UseSkillOut
from app.services import skill_service

router = APIRouter(prefix="/api/v1/skills", tags=["skills"])


@router.post("", response_model=SkillOut, status_code=201)
async def create_skill(body: SkillCreateIn, actor: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    return await skill_service.create_skill(db, actor, **body.model_dump())


@router.get("", response_model=list[SkillOut])
async def list_skills(actor: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    return await skill_service.list_skills(db, actor)


@router.post("/{skill_id}/versions", status_code=201)
async def add_version(skill_id: uuid.UUID, body: SkillVersionIn,
                      actor: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    version = await skill_service.add_version(db, actor, skill_id, body.content)
    return {"version": version}


@router.post("/{skill_id}/grants")
async def grant(skill_id: uuid.UUID, body: SkillGrantIn,
                actor: User = Depends(get_current_user),
                db: AsyncSession = Depends(get_db)):
    created = await skill_service.grant_skill(db, actor, skill_id, body.user_id)
    return Response(status_code=201 if created else 200)


@router.get("/{skill_id}/use", response_model=UseSkillOut)
async def use_skill(skill_id: uuid.UUID, actor: User = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)):
    return await skill_service.use_skill(db, actor, skill_id)
