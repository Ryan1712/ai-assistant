import pytest
from fastapi import HTTPException

from app.models import Role, User, Workspace
from app.services import auth_service


@pytest.mark.asyncio
async def test_login_rejects_user_without_password_cleanly(db_session):
    """Nhân viên chỉ-có-tên (Task 3: add_employee) có password_hash=None. Nếu login()
    gọi thẳng security.verify_password(password, None) sẽ AttributeError (None không
    có .encode()) — lỗi hệ thống 500 thay vì từ chối sạch 401. Đây là defense-in-depth:
    record chỉ-tên TUYỆT ĐỐI không được đăng nhập, dù ai đó biết email và đoán đúng gì đó."""
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    nv = User(workspace_id=ws.id, email="nv@a.vn", password_hash=None,
             full_name="Nhan Vien", role=Role.employee)
    db_session.add(nv)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await auth_service.login(db_session, email="nv@a.vn", password="anything",
                                 device_uuid="d", device_name="")
    assert exc.value.status_code == 401
    assert exc.value.detail == "invalid_credentials"
