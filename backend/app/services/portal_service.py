"""Cổng báo cáo CEO ceo.9learning.edu.vn (funtional-plan 6.8).

Chỉ CEO của đúng workspace + gói Advanced. Chưa có API spec thật của cổng →
HttpPortalClient là best-effort, mặc định chạy MockPortalClient
(settings.portal_mock=True) để agent/FE phát triển trước.
"""
from typing import Protocol, TypedDict

import httpx
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import plans
from app.config import get_settings
from app.models import User, Workspace
from app.permissions import require_ceo


class PortalReport(TypedDict):
    id: str
    title: str
    period: str
    summary: str
    data: dict


class PortalClient(Protocol):
    async def list_reports(self) -> list[PortalReport]: ...
    async def get_report(self, report_id: str) -> PortalReport | None: ...


_MOCK_REPORTS: list[PortalReport] = [
    {"id": "rev-2026-w28", "title": "Báo cáo doanh thu tuần 28/2026",
     "period": "2026-07-06..2026-07-12",
     "summary": "Doanh thu tuần đạt 1.24 tỷ, tăng 8% so với tuần trước.",
     "data": {"revenue_vnd": 1_240_000_000, "growth_pct": 8.0,
              "top_product": "Khóa học AI Foundation"}},
    {"id": "ops-2026-w28", "title": "Báo cáo vận hành tuần 28/2026",
     "period": "2026-07-06..2026-07-12",
     "summary": "Tỷ lệ hoàn thành lớp học 96%, 2 sự cố hạ tầng đã xử lý.",
     "data": {"class_completion_pct": 96, "incidents": 2, "nps": 71}},
]


class MockPortalClient:
    async def list_reports(self) -> list[PortalReport]:
        return list(_MOCK_REPORTS)

    async def get_report(self, report_id: str) -> PortalReport | None:
        return next((r for r in _MOCK_REPORTS if r["id"] == report_id), None)


class HttpPortalClient:
    def __init__(self, base_url: str):
        self._base_url = base_url.rstrip("/")

    async def list_reports(self) -> list[PortalReport]:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{self._base_url}/api/reports")
            resp.raise_for_status()
            return resp.json()

    async def get_report(self, report_id: str) -> PortalReport | None:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{self._base_url}/api/reports/{report_id}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()


def get_portal_client() -> PortalClient:
    settings = get_settings()
    if settings.portal_mock:
        return MockPortalClient()
    return HttpPortalClient(settings.portal_base_url)


async def _authorize(db: AsyncSession, actor: User) -> None:
    require_ceo(actor)
    ws = await db.get(Workspace, actor.workspace_id)
    if not plans.plan_allows(ws, "ceo_portal"):
        raise HTTPException(403, "advanced_plan_required")


async def list_reports(db: AsyncSession, actor: User) -> list[PortalReport]:
    await _authorize(db, actor)
    return await get_portal_client().list_reports()


async def get_report(db: AsyncSession, actor: User, report_id: str) -> PortalReport:
    await _authorize(db, actor)
    report = await get_portal_client().get_report(report_id)
    if report is None:
        raise HTTPException(404, "portal_report_not_found")
    return report
