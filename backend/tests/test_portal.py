import pytest

from tests.conftest import _ceo_headers, _invite_and_join


def _h(j):
    return {"Authorization": f"Bearer {j['access_token']}"}


async def _advanced(client, ceo_h):
    r = await client.patch("/api/v1/subscription", headers=ceo_h, json={"plan": "advanced"})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_ceo_advanced_reads_mock_reports(client):
    ceo_h = await _ceo_headers(client)
    await _advanced(client, ceo_h)
    listed = await client.get("/api/v1/portal/reports", headers=ceo_h)
    assert listed.status_code == 200, listed.text
    reports = listed.json()
    assert len(reports) >= 1
    rid = reports[0]["id"]
    detail = await client.get(f"/api/v1/portal/reports/{rid}", headers=ceo_h)
    assert detail.status_code == 200
    assert "data" in detail.json()


@pytest.mark.asyncio
async def test_basic_plan_blocked(client):
    ceo_h = await _ceo_headers(client)
    r = await client.get("/api/v1/portal/reports", headers=ceo_h)
    assert r.status_code == 403
    assert r.json()["detail"] == "advanced_plan_required"


@pytest.mark.asyncio
async def test_non_ceo_blocked_even_on_advanced(client):
    ceo_h = await _ceo_headers(client)
    await _advanced(client, ceo_h)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    r = await client.get("/api/v1/portal/reports", headers=_h(m1))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_agent_tools_portal(db_session):
    from app.agent.tools import call_tool
    from app.models import Role, User, Workspace, WorkspacePlan

    ws = Workspace(name="A", plan=WorkspacePlan.advanced)
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
               role=Role.ceo, is_root=True)
    emp = User(workspace_id=ws.id, email="e@a.vn", password_hash="x", full_name="E",
               role=Role.employee)
    db_session.add_all([ceo, emp])
    await db_session.commit()

    listed = await call_tool(db_session, ceo, "list_portal_reports", {})
    assert len(listed["reports"]) >= 1
    rid = listed["reports"][0]["id"]
    detail = await call_tool(db_session, ceo, "get_portal_report", {"report_id": rid})
    assert detail["id"] == rid

    denied = await call_tool(db_session, emp, "list_portal_reports", {})
    assert denied["error"] == "forbidden"
