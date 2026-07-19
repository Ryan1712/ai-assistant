import pytest
from fastapi import HTTPException

from app.models import Role, User, Workspace
from app.services import instruction_service


async def _make_ws(db, name="A", email_prefix="a"):
    ws = Workspace(name=name)
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email=f"ceo@{email_prefix}.vn", password_hash="x",
               full_name="Sep", role=Role.ceo, is_root=True)
    emp = User(workspace_id=ws.id, email=f"e1@{email_prefix}.vn", password_hash="x",
               full_name="NV", role=Role.employee)
    db.add_all([ceo, emp])
    await db.commit()
    return ws, ceo, emp


@pytest.mark.asyncio
async def test_ceo_creates_instruction_v1(db_session):
    ws, ceo, _ = await _make_ws(db_session)
    ins = await instruction_service.create_instruction(
        db_session, ceo, title="Giong dieu", content="Tra loi ngan gon")
    assert ins.version == 1
    listed = await instruction_service.list_instructions(db_session, ceo)
    assert len(listed) == 1
    assert listed[0]["content"] == "Tra loi ngan gon"


@pytest.mark.asyncio
async def test_update_bumps_version_and_active_text_is_latest(db_session):
    ws, ceo, _ = await _make_ws(db_session)
    ins = await instruction_service.create_instruction(db_session, ceo, "Quy tac", "v1 noi dung")
    v = await instruction_service.update_instruction(db_session, ceo, ins.id, "v2 noi dung")
    assert v == 2
    text = await instruction_service.active_instructions_text(db_session, ws.id)
    assert "v2 noi dung" in text
    assert "v1 noi dung" not in text
    assert "Quy tac" in text


@pytest.mark.asyncio
async def test_non_ceo_forbidden(db_session):
    ws, ceo, emp = await _make_ws(db_session)
    ins = await instruction_service.create_instruction(db_session, ceo, "T", "c")
    for coro in [
        instruction_service.create_instruction(db_session, emp, "X", "y"),
        instruction_service.update_instruction(db_session, emp, ins.id, "z"),
        instruction_service.list_instructions(db_session, emp),
        instruction_service.delete_instruction(db_session, emp, ins.id),
    ]:
        with pytest.raises(HTTPException) as ei:
            await coro
        assert ei.value.status_code == 403


@pytest.mark.asyncio
async def test_cross_workspace_isolated(db_session):
    ws_a, ceo_a, _ = await _make_ws(db_session, "A", "a")
    ws_b, ceo_b, _ = await _make_ws(db_session, "B", "b")
    ins = await instruction_service.create_instruction(db_session, ceo_a, "T", "noi dung A")
    assert await instruction_service.list_instructions(db_session, ceo_b) == []
    with pytest.raises(HTTPException) as ei:
        await instruction_service.update_instruction(db_session, ceo_b, ins.id, "hack")
    assert ei.value.status_code == 404
    assert "noi dung A" not in await instruction_service.active_instructions_text(
        db_session, ws_b.id)


@pytest.mark.asyncio
async def test_delete_removes_from_active_text(db_session):
    ws, ceo, _ = await _make_ws(db_session)
    ins = await instruction_service.create_instruction(db_session, ceo, "T", "se bi xoa")
    await instruction_service.delete_instruction(db_session, ceo, ins.id)
    assert "se bi xoa" not in await instruction_service.active_instructions_text(
        db_session, ws.id)
    assert await instruction_service.list_instructions(db_session, ceo) == []


@pytest.mark.asyncio
async def test_active_instructions_bi_cap_do_dai(db_session):
    ws, ceo, _ = await _make_ws(db_session)
    await instruction_service.create_instruction(
        db_session, ceo, title="Dai qua", content="x" * 20000)
    text = await instruction_service.active_instructions_text(db_session, ws.id)
    assert len(text) <= 8000 + 100  # 8000 + dong ghi chu bi cat
    assert "bị cắt" in text
