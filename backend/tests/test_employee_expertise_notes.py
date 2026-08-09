"""suggest_assignee (spec docs/superpowers/specs/2026-08-09-suggest-assignee-design.md):
User.expertise_notes là chuyên môn nhân viên (text tự do, CEO tự nhập) --
KHÔNG liên quan gì tới bảng Skill (tài liệu/kiến thức AI dùng khi trả lời),
tên field cố ý tránh chữ "skill" để không gây nhầm lẫn 2 khái niệm."""
import pytest
from sqlalchemy import select

from app.models import Embedding, Role, User, Workspace
from app.services import auth_service, embedding_service
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


@pytest.mark.asyncio
async def test_index_employee_expertise_creates_embedding(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    user = User(workspace_id=ws.id, full_name="Duy Linh", role=Role.employee,
               expertise_notes="design, figma, frontend react")
    db_session.add(user)
    await db_session.commit()

    await embedding_service.index_employee_expertise(db_session, ws.id, user)

    row = (await db_session.execute(select(Embedding).where(
        Embedding.source_type == "employee_expertise", Embedding.source_id == user.id
    ))).scalar_one_or_none()
    assert row is not None
    assert row.content == "design, figma, frontend react"


@pytest.mark.asyncio
async def test_index_employee_expertise_skips_when_none(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    user = User(workspace_id=ws.id, full_name="No Expertise", role=Role.employee,
               expertise_notes=None)
    db_session.add(user)
    await db_session.commit()

    await embedding_service.index_employee_expertise(db_session, ws.id, user)

    row = (await db_session.execute(select(Embedding).where(
        Embedding.source_type == "employee_expertise", Embedding.source_id == user.id
    ))).scalar_one_or_none()
    assert row is None


@pytest.mark.asyncio
async def test_update_employee_expertise_reindexes(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db_session.add(ceo)
    await db_session.flush()
    emp = User(workspace_id=ws.id, full_name="Duy Linh", role=Role.employee,
              expertise_notes="design")
    db_session.add(emp)
    await db_session.commit()
    await embedding_service.index_employee_expertise(db_session, ws.id, emp)

    updated = await auth_service.update_employee_expertise(
        db_session, actor=ceo, user_id=emp.id, expertise_notes="backend python")

    assert updated.expertise_notes == "backend python"
    row = (await db_session.execute(select(Embedding).where(
        Embedding.source_type == "employee_expertise", Embedding.source_id == emp.id
    ))).scalar_one()
    assert row.content == "backend python"


@pytest.mark.asyncio
async def test_update_employee_expertise_requires_ceo(db_session):
    from fastapi import HTTPException

    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    manager = User(workspace_id=ws.id, email="m@a.vn", password_hash="x", full_name="M",
                   role=Role.manager)
    emp = User(workspace_id=ws.id, full_name="E", role=Role.employee)
    db_session.add_all([manager, emp])
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await auth_service.update_employee_expertise(
            db_session, actor=manager, user_id=emp.id, expertise_notes="x")
    assert exc.value.status_code == 403
