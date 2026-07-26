import pytest
from fastapi import HTTPException

from app.models import Invite, Role, User, UserStatus, Workspace
from app.services import auth_service
from sqlalchemy import select
from tests.conftest import SIGNUP, _ceo_headers, _invite_and_join


async def _ceo(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    await db.commit()
    return ws, ceo


@pytest.mark.asyncio
async def test_add_employee_with_name_only(db_session):
    ws, ceo = await _ceo(db_session)
    user = await auth_service.add_employee(db_session, actor=ceo, full_name="Duy Linh")
    assert user.full_name == "Duy Linh"
    assert user.email is None
    assert user.password_hash is None
    assert user.status == UserStatus.active
    assert user.role == Role.employee
    assert user.workspace_id == ws.id


@pytest.mark.asyncio
async def test_add_employee_with_name_and_email(db_session):
    ws, ceo = await _ceo(db_session)
    user = await auth_service.add_employee(db_session, actor=ceo, full_name="Nam",
                                           email="nam@a.vn")
    assert user.email == "nam@a.vn"
    assert user.password_hash is None


@pytest.mark.asyncio
async def test_add_employee_no_activation_code_or_invite_row(db_session):
    """Khác hẳn create_employee cũ: KHÔNG sinh Invite/mã kích hoạt gì."""
    ws, ceo = await _ceo(db_session)
    await auth_service.add_employee(db_session, actor=ceo, full_name="Duy Linh")
    invites = (await db_session.execute(select(Invite))).scalars().all()
    assert invites == []


@pytest.mark.asyncio
async def test_add_employee_duplicate_email_409(db_session):
    ws, ceo = await _ceo(db_session)
    await auth_service.add_employee(db_session, actor=ceo, full_name="A", email="dup@a.vn")
    with pytest.raises(HTTPException) as exc:
        await auth_service.add_employee(db_session, actor=ceo, full_name="B", email="dup@a.vn")
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_non_ceo_cannot_add_employee(db_session):
    ws, ceo = await _ceo(db_session)
    mgr = User(workspace_id=ws.id, email="m@a.vn", password_hash="x", full_name="M",
              role=Role.manager)
    db_session.add(mgr)
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await auth_service.add_employee(db_session, actor=mgr, full_name="X")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_added_employee_cannot_login(db_session):
    """End-to-end với guard Task 1: nhân viên vừa thêm không đăng nhập được."""
    ws, ceo = await _ceo(db_session)
    await auth_service.add_employee(db_session, actor=ceo, full_name="Duy Linh",
                                    email="duy@a.vn")
    with pytest.raises(HTTPException) as exc:
        await auth_service.login(db_session, email="duy@a.vn", password="anything",
                                 device_uuid="d", device_name="")
    assert exc.value.status_code == 401
