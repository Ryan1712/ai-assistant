import pytest

from tests.conftest import SIGNUP, _ceo_headers, _invite_and_join


async def _advanced_ceo_headers(client):
    headers = await _ceo_headers(client)
    r = await client.patch("/api/v1/subscription", headers=headers, json={"plan": "advanced"})
    assert r.status_code == 200
    return headers


@pytest.mark.asyncio
async def test_create_list_delete_report_schedule_via_rest(client):
    headers = await _advanced_ceo_headers(client)

    r = await client.post("/api/v1/report-schedules", headers=headers,
                          json={"weekday": 0, "hour": 8, "minute": 0})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert r.json()["weekday"] == 0

    r2 = await client.get("/api/v1/report-schedules", headers=headers)
    assert r2.status_code == 200
    assert [s["id"] for s in r2.json()] == [sid]

    r3 = await client.delete(f"/api/v1/report-schedules/{sid}", headers=headers)
    assert r3.status_code == 204

    r4 = await client.get("/api/v1/report-schedules", headers=headers)
    assert r4.json() == []


@pytest.mark.asyncio
async def test_basic_plan_workspace_gets_403(client):
    headers = await _ceo_headers(client)  # mặc định Basic

    r = await client.post("/api/v1/report-schedules", headers=headers,
                          json={"weekday": None, "hour": 8})
    assert r.status_code == 403
    assert r.json()["detail"] == "advanced_plan_required"


@pytest.mark.asyncio
async def test_employee_cannot_manage_report_schedule(client):
    headers = await _advanced_ceo_headers(client)
    mgr = await _invite_and_join(client, headers, "manager", "m@a.vn")
    emp = await _invite_and_join(client, headers, "employee", "nv@a.vn",
                                 manager_id=mgr["user"]["id"])
    emp_headers = {"Authorization": f"Bearer {emp['access_token']}"}

    r = await client.post("/api/v1/report-schedules", headers=emp_headers,
                          json={"weekday": None, "hour": 8})
    assert r.status_code == 403

    r2 = await client.get("/api/v1/report-schedules", headers=emp_headers)
    assert r2.status_code == 403


@pytest.mark.asyncio
async def test_invalid_hour_rejected_by_schema(client):
    headers = await _advanced_ceo_headers(client)
    r = await client.post("/api/v1/report-schedules", headers=headers,
                          json={"weekday": None, "hour": 25})
    assert r.status_code == 422
