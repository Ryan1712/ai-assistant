import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models import Directive, DirectiveStatus, Notification, Role, User, Workspace
from app.services import directive_service


async def _world(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    duy = User(workspace_id=ws.id, email="d@a.vn", password_hash="x", full_name="Duy",
              role=Role.employee)
    other = User(workspace_id=ws.id, email="o@a.vn", password_hash="x", full_name="Khac",
                role=Role.employee)
    db.add_all([ceo, duy, other])
    await db.flush()
    directive = Directive(workspace_id=ws.id, created_by=ceo.id, recipient_id=duy.id,
                          verbatim_text="lam viec X")
    db.add(directive)
    await db.commit()
    return ws, ceo, duy, other, directive


@pytest.mark.asyncio
async def test_ack_directive_by_recipient(db_session):
    ws, ceo, duy, other, directive = await _world(db_session)

    out = await directive_service.ack_directive(db_session, duy, directive.id)

    await db_session.refresh(directive)
    assert directive.status == DirectiveStatus.acked
    assert directive.acked_at is not None
    assert out["status"] == "acked"
    notif = (await db_session.execute(
        select(Notification).where(Notification.type == "directive_acked"))).scalar_one()
    assert notif.recipient_id == ceo.id


@pytest.mark.asyncio
async def test_ack_directive_by_non_recipient_404(db_session):
    ws, ceo, duy, other, directive = await _world(db_session)

    with pytest.raises(HTTPException) as exc:
        await directive_service.ack_directive(db_session, other, directive.id)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_ack_directive_already_acked_409(db_session):
    ws, ceo, duy, other, directive = await _world(db_session)
    await directive_service.ack_directive(db_session, duy, directive.id)

    with pytest.raises(HTTPException) as exc:
        await directive_service.ack_directive(db_session, duy, directive.id)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_raise_question_by_recipient(db_session):
    ws, ceo, duy, other, directive = await _world(db_session)

    out = await directive_service.raise_question(db_session, duy, directive.id, "Deadline nao?")

    await db_session.refresh(directive)
    assert directive.status == DirectiveStatus.question
    assert directive.response_text == "Deadline nao?"
    assert out["response_text"] == "Deadline nao?"
    notif = (await db_session.execute(
        select(Notification).where(Notification.type == "directive_question"))).scalar_one()
    assert notif.payload["question"] == "Deadline nao?"


@pytest.mark.asyncio
async def test_renegotiate_by_recipient(db_session):
    ws, ceo, duy, other, directive = await _world(db_session)
    new_deadline = datetime(2026, 8, 1, tzinfo=timezone.utc)

    out = await directive_service.renegotiate(db_session, duy, directive.id,
                                              "Ban qua nhieu viec",
                                              new_deadline_proposal=new_deadline)

    await db_session.refresh(directive)
    assert directive.status == DirectiveStatus.renegotiate
    assert directive.response_text == "Ban qua nhieu viec"
    notif = (await db_session.execute(
        select(Notification).where(Notification.type == "directive_renegotiate"))).scalar_one()
    assert notif.payload["proposal"] == new_deadline.isoformat()


@pytest.mark.asyncio
async def test_renegotiate_without_specific_deadline(db_session):
    """V1 (spec §7.5): 'xin dời hạn' chỉ cần lý do bằng lời — không bắt buộc ngày cụ thể."""
    ws, ceo, duy, other, directive = await _world(db_session)

    out = await directive_service.renegotiate(db_session, duy, directive.id, "Cho toi them 2 ngay")

    await db_session.refresh(directive)
    assert directive.status == DirectiveStatus.renegotiate
    assert directive.response_text == "Cho toi them 2 ngay"
    notif = (await db_session.execute(
        select(Notification).where(Notification.type == "directive_renegotiate"))).scalar_one()
    assert notif.payload["proposal"] is None


@pytest.mark.asyncio
async def test_ack_directive_not_found_for_wrong_workspace(db_session):
    ws, ceo, duy, other, directive = await _world(db_session)
    with pytest.raises(HTTPException) as exc:
        await directive_service.ack_directive(db_session, duy, uuid.uuid4())
    assert exc.value.status_code == 404
