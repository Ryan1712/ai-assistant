import pytest
from sqlalchemy import select

from app.models import Directive, DirectiveStatus, EmailMessage, Notification, Project, Role, Task, User, Workspace
from app.services import directive_service


async def _world(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    mgr = User(workspace_id=ws.id, email="m@a.vn", password_hash="x", full_name="Ha",
              role=Role.manager)
    db.add_all([ceo, mgr])
    await db.flush()
    duy = User(workspace_id=ws.id, email="d@a.vn", password_hash="x", full_name="Duy",
              role=Role.employee, manager_id=mgr.id)
    other_mgr = User(workspace_id=ws.id, email="m2@a.vn", password_hash="x", full_name="M2",
                     role=Role.manager)
    db.add_all([duy, other_mgr])
    await db.flush()
    nam = User(workspace_id=ws.id, email="n@a.vn", password_hash="x", full_name="Nam",
              role=Role.employee, manager_id=other_mgr.id)
    db.add(nam)
    await db.flush()
    project = Project(workspace_id=ws.id, name="P", created_by=ceo.id)
    db.add(project)
    await db.flush()
    task = Task(workspace_id=ws.id, project_id=project.id, title="Thiet ke landing page",
               created_by=ceo.id)
    db.add(task)
    await db.flush()
    await db.commit()
    return ws, ceo, mgr, duy, other_mgr, nam, task


@pytest.mark.asyncio
async def test_ceo_creates_directive_for_employee(db_session):
    ws, ceo, mgr, duy, other_mgr, nam, task = await _world(db_session)

    out = await directive_service.create_directive(
        db_session, ceo, recipient_id=duy.id, task_id=task.id,
        verbatim_text="Duy xong deadline nhe", structured_summary="Doi han task X")

    directive = (await db_session.execute(select(Directive))).scalar_one()
    assert directive.status == DirectiveStatus.sent
    assert directive.created_by == ceo.id
    assert directive.recipient_id == duy.id
    assert directive.task_id == task.id
    assert out["id"] == str(directive.id)

    notif = (await db_session.execute(
        select(Notification).where(Notification.type == "directive_assigned"))).scalar_one()
    assert notif.recipient_id == duy.id
    assert notif.payload["directive_id"] == str(directive.id)

    email = (await db_session.execute(select(EmailMessage))).scalar_one()
    assert email.recipient_id == duy.id
    assert email.sender_id == ceo.id


@pytest.mark.asyncio
async def test_manager_creates_directive_for_own_direct_report(db_session):
    ws, ceo, mgr, duy, other_mgr, nam, task = await _world(db_session)

    out = await directive_service.create_directive(
        db_session, mgr, recipient_id=duy.id, verbatim_text="Lam viec X")

    directive = (await db_session.execute(select(Directive))).scalar_one()
    assert directive.created_by == mgr.id
    assert directive.task_id is None


@pytest.mark.asyncio
async def test_manager_cannot_create_directive_for_other_managers_report(db_session):
    from fastapi import HTTPException
    ws, ceo, mgr, duy, other_mgr, nam, task = await _world(db_session)

    with pytest.raises(HTTPException) as exc:
        await directive_service.create_directive(
            db_session, mgr, recipient_id=nam.id, verbatim_text="x")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_employee_cannot_create_directive(db_session):
    from fastapi import HTTPException
    ws, ceo, mgr, duy, other_mgr, nam, task = await _world(db_session)

    with pytest.raises(HTTPException) as exc:
        await directive_service.create_directive(
            db_session, duy, recipient_id=nam.id, verbatim_text="x")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_create_directive_recipient_not_found(db_session):
    from fastapi import HTTPException
    import uuid
    ws, ceo, mgr, duy, other_mgr, nam, task = await _world(db_session)

    with pytest.raises(HTTPException) as exc:
        await directive_service.create_directive(
            db_session, ceo, recipient_id=uuid.uuid4(), verbatim_text="x")
    assert exc.value.status_code == 404
