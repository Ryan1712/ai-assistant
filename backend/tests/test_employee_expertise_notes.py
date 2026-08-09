"""suggest_assignee (spec docs/superpowers/specs/2026-08-09-suggest-assignee-design.md):
User.expertise_notes là chuyên môn nhân viên (text tự do, CEO tự nhập) --
KHÔNG liên quan gì tới bảng Skill (tài liệu/kiến thức AI dùng khi trả lời),
tên field cố ý tránh chữ "skill" để không gây nhầm lẫn 2 khái niệm."""
import pytest

from tests.conftest import _ceo_headers


@pytest.mark.asyncio
async def test_add_employee_with_expertise_notes(client):
    ceo_h = await _ceo_headers(client)
    resp = await client.post("/api/v1/employees", headers=ceo_h,
                             json={"full_name": "Duy Linh",
                                   "expertise_notes": "design, figma, frontend react"})
    assert resp.status_code == 201
    assert resp.json()["expertise_notes"] == "design, figma, frontend react"


@pytest.mark.asyncio
async def test_add_employee_without_expertise_notes_defaults_none(client):
    ceo_h = await _ceo_headers(client)
    resp = await client.post("/api/v1/employees", headers=ceo_h,
                             json={"full_name": "No Expertise Guy"})
    assert resp.status_code == 201
    assert resp.json()["expertise_notes"] is None


@pytest.mark.asyncio
async def test_list_users_includes_expertise_notes(client):
    ceo_h = await _ceo_headers(client)
    await client.post("/api/v1/employees", headers=ceo_h,
                      json={"full_name": "Duy Linh", "expertise_notes": "backend python"})
    listed = (await client.get("/api/v1/users", headers=ceo_h)).json()
    duy = next(u for u in listed if u["full_name"] == "Duy Linh")
    assert duy["expertise_notes"] == "backend python"
