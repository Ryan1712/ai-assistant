import pytest

from tests.conftest import _ceo_headers


@pytest.mark.asyncio
async def test_search_finds_own_task_and_note(client):
    headers = await _ceo_headers(client)
    p = (await client.post("/api/v1/projects", headers=headers, json={"name": "P"})).json()
    await client.post("/api/v1/tasks", headers=headers,
                      json={"project_id": p["id"], "title": "Sua loi website"})
    await client.post("/api/v1/notes", headers=headers, json={"content": "ghi chu website"})

    r = await client.get("/api/v1/search", headers=headers, params={"q": "website"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert [t["title"] for t in body["tasks"]] == ["Sua loi website"]
    assert [n["content"] for n in body["notes"]] == ["ghi chu website"]
    assert body["voice_notes"] == [] and body["users"] == [] and body["skills"] == []


@pytest.mark.asyncio
async def test_search_empty_query_rejected(client):
    headers = await _ceo_headers(client)
    r = await client.get("/api/v1/search", headers=headers, params={"q": ""})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_search_cross_workspace_isolated(client):
    ceo_a = await _ceo_headers(client)
    p = (await client.post("/api/v1/projects", headers=ceo_a, json={"name": "P"})).json()
    await client.post("/api/v1/tasks", headers=ceo_a,
                      json={"project_id": p["id"], "title": "Bi mat cong ty A"})

    resp_b = await client.post("/api/v1/auth/signup-workspace", json={
        "workspace_name": "Cong ty B", "email": "ceo@b.vn", "password": "secret123",
        "full_name": "Sep B", "device_uuid": "dev-b", "device_name": "",
    })
    ceo_b = {"Authorization": f"Bearer {resp_b.json()['access_token']}"}

    r = await client.get("/api/v1/search", headers=ceo_b, params={"q": "bi mat"})
    assert r.status_code == 200
    assert r.json()["tasks"] == []
