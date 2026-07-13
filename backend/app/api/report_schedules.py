import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import ReportScheduleCreateIn, ReportScheduleOut
from app.services import report_schedule_service

router = APIRouter(prefix="/api/v1/report-schedules", tags=["report-schedules"])


@router.post("", response_model=ReportScheduleOut, status_code=201)
async def create_report_schedule(body: ReportScheduleCreateIn,
                                 actor: User = Depends(get_current_user),
                                 db: AsyncSession = Depends(get_db)):
    return await report_schedule_service.create_schedule(db, actor, **body.model_dump())


@router.get("", response_model=list[ReportScheduleOut])
async def list_report_schedules(actor: User = Depends(get_current_user),
                                db: AsyncSession = Depends(get_db)):
    return await report_schedule_service.list_schedules(db, actor)


@router.delete("/{schedule_id}", status_code=204)
async def delete_report_schedule(schedule_id: uuid.UUID,
                                 actor: User = Depends(get_current_user),
                                 db: AsyncSession = Depends(get_db)):
    await report_schedule_service.delete_schedule(db, actor, schedule_id)
    return Response(status_code=204)
