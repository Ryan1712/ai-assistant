import uuid

import pytest
from sqlalchemy import select

from app.models import User
from app.services import report_service
from tests.conftest import _ceo_headers, _invite_and_join

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


async def _make_report(client, db_session):
    """Signup CEO qua API rồi tạo report qua service (cùng engine → cùng DB)."""
    headers = await _ceo_headers(client)
    ceo = (await db_session.execute(
        select(User).where(User.email == "ceo@a.vn"))).scalar_one()
    result = await report_service.generate_report(db_session, ceo)
    return headers, result["report_id"]


@pytest.mark.asyncio
async def test_ceo_downloads_xlsx(client, db_session, storage_dir):
    headers, report_id = await _make_report(client, db_session)
    resp = await client.get(f"/api/v1/reports/{report_id}/download", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == XLSX
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.content[:2] == b"PK"  # magic bytes zip/xlsx


@pytest.mark.asyncio
async def test_non_ceo_gets_404(client, db_session, storage_dir):
    headers, report_id = await _make_report(client, db_session)
    mgr = await _invite_and_join(client, headers, "manager", "m@a.vn")
    emp = await _invite_and_join(client, headers, "employee", "e@a.vn",
                                 manager_id=mgr["user"]["id"])
    emp_headers = {"Authorization": f"Bearer {emp['access_token']}"}
    resp = await client.get(f"/api/v1/reports/{report_id}/download",
                            headers=emp_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_unknown_report_404(client, storage_dir):
    headers = await _ceo_headers(client)
    resp = await client.get(f"/api/v1/reports/{uuid.uuid4()}/download", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_missing_file_on_disk_404(client, db_session, storage_dir):
    headers, report_id = await _make_report(client, db_session)
    for f in storage_dir.rglob("*.xlsx"):
        f.unlink()
    resp = await client.get(f"/api/v1/reports/{report_id}/download", headers=headers)
    assert resp.status_code == 404
