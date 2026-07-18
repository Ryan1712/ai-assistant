from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import _ceo_headers, _invite_and_join


def _h(j):
    return {"Authorization": f"Bearer {j['access_token']}"}


@pytest.mark.asyncio
async def test_create_and_list_own_notes(client):
    ceo_h = await _ceo_headers(client)
    r = await client.post("/api/v1/notes", headers=ceo_h,
                          json={"content": "Hop voi doi tac", "tags": ["meeting"]})
    assert r.status_code == 201, r.text
    # Server mac dinh note_date theo ngay lich VN (models._today, UTC+7) khi
    # client khong truyen — dung date.today() (gio local may chay test, co the
    # khac VN) se sai lech, phai tu quy doi giong _today() de test on dinh.
    vn_today = (datetime.now(timezone.utc) + timedelta(hours=7)).date()
    assert r.json()["note_date"] == vn_today.isoformat()

    listed = await client.get("/api/v1/notes", headers=ceo_h)
    assert len(listed.json()) == 1
    assert listed.json()[0]["content"] == "Hop voi doi tac"


@pytest.mark.asyncio
async def test_notes_are_private_even_from_ceo(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    await client.post("/api/v1/notes", headers=_h(m1), json={"content": "note rieng"})
    assert (await client.get("/api/v1/notes", headers=ceo_h)).json() == []
    assert len((await client.get("/api/v1/notes", headers=_h(m1))).json()) == 1


@pytest.mark.asyncio
async def test_filter_by_date_and_tag(client):
    ceo_h = await _ceo_headers(client)
    await client.post("/api/v1/notes", headers=ceo_h,
                      json={"content": "hom qua", "note_date": "2026-07-11", "tags": ["a"]})
    await client.post("/api/v1/notes", headers=ceo_h,
                      json={"content": "hom nay", "tags": ["b"]})
    by_date = await client.get("/api/v1/notes", headers=ceo_h,
                               params={"on_date": "2026-07-11"})
    assert [n["content"] for n in by_date.json()] == ["hom qua"]
    by_tag = await client.get("/api/v1/notes", headers=ceo_h, params={"tag": "b"})
    assert [n["content"] for n in by_tag.json()] == ["hom nay"]


@pytest.mark.asyncio
async def test_note_linked_task_must_be_visible(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    p = await client.post("/api/v1/projects", headers=ceo_h, json={"name": "P"})
    t = await client.post("/api/v1/tasks", headers=ceo_h,
                          json={"project_id": p.json()["id"], "title": "T"})
    task_id = t.json()["id"]
    # m1 không được giao task → không gắn note vào task đó được
    r = await client.post("/api/v1/notes", headers=_h(m1),
                          json={"content": "x", "task_id": task_id})
    assert r.status_code == 404
    # CEO thì được
    ok = await client.post("/api/v1/notes", headers=ceo_h,
                           json={"content": "x", "task_id": task_id})
    assert ok.status_code == 201
    assert ok.json()["task_id"] == task_id
