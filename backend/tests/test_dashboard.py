from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import _ceo_headers, _invite_and_join


def _h(j):
    return {"Authorization": f"Bearer {j['access_token']}"}


async def _setup_world(client):
    """Project + 3 task: due hôm nay (giao e1), quá hạn, đang làm. e1 có 1 update."""
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    e1 = await _invite_and_join(client, ceo_h, "employee", "e1@a.vn", m1["user"]["id"])
    p = (await client.post("/api/v1/projects", headers=ceo_h, json={"name": "P"})).json()
    now = datetime.now(timezone.utc)

    due_today = (await client.post("/api/v1/tasks", headers=ceo_h, json={
        "project_id": p["id"], "title": "Due hom nay",
        "deadline": (now + timedelta(hours=2)).isoformat()})).json()
    overdue = (await client.post("/api/v1/tasks", headers=ceo_h, json={
        "project_id": p["id"], "title": "Qua han",
        "deadline": (now - timedelta(days=2)).isoformat()})).json()
    doing = (await client.post("/api/v1/tasks", headers=ceo_h, json={
        "project_id": p["id"], "title": "Dang lam"})).json()
    await client.patch(f"/api/v1/tasks/{doing['id']}", headers=ceo_h,
                       json={"status": "in_progress"})
    await client.post(f"/api/v1/tasks/{due_today['id']}/assignees", headers=ceo_h,
                      json={"user_id": e1["user"]["id"]})
    await client.post(f"/api/v1/tasks/{due_today['id']}/updates", headers=_h(e1),
                      json={"content": "dang chay", "percent": 30})
    return ceo_h, m1, e1, due_today, overdue, doing


@pytest.mark.asyncio
async def test_ceo_sees_everything(client):
    ceo_h, m1, e1, due_today, overdue, doing = await _setup_world(client)
    r = await client.get("/api/v1/dashboard/today", headers=ceo_h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert [t["title"] for t in d["due_today"]] == ["Due hom nay"]
    assert [t["title"] for t in d["overdue"]] == ["Qua han"]
    assert [t["title"] for t in d["in_progress"]] == ["Dang lam"]
    assert d["counters"]["overdue"] == 1
    assert d["counters"]["updates_24h"] == 1
    assert d["recent_updates"][0]["content"] == "dang chay"
    assert d["recent_updates"][0]["task_title"] == "Due hom nay"
    assert d["notes_today"] == []


@pytest.mark.asyncio
async def test_employee_scope_limited_to_own_tasks(client):
    ceo_h, m1, e1, due_today, overdue, doing = await _setup_world(client)
    await client.post("/api/v1/notes", headers=_h(e1), json={"content": "note cua e1"})
    d = (await client.get("/api/v1/dashboard/today", headers=_h(e1))).json()
    assert [t["title"] for t in d["due_today"]] == ["Due hom nay"]
    assert d["overdue"] == []
    assert d["in_progress"] == []
    assert d["counters"]["waiting_on_me"] == 1
    assert [n["content"] for n in d["notes_today"]] == ["note cua e1"]


@pytest.mark.asyncio
async def test_dashboard_agent_tool(db_session):
    from app.agent.tools import call_tool
    from app.models import Role, User, Workspace

    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
               role=Role.ceo, is_root=True)
    db_session.add(ceo)
    await db_session.commit()
    got = await call_tool(db_session, ceo, "get_today_dashboard", {})
    assert got["counters"] == {"overdue": 0, "waiting_on_me": 0, "updates_24h": 0}
