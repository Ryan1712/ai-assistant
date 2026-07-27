import pytest
from fastapi import HTTPException

from app.models import Role, User, UserStatus, Workspace
from app.services import auth_service


class _FakeRedis:
    """Redis in-memory tối thiểu cho test (không TTL — không kiểm hết hạn ở đây).
    Cùng interface với tests/test_password_reset.py::_FakeRedis, khai báo riêng ở
    đây vì test này gọi thẳng auth_service.forgot_password/reset_password (không
    qua HTTP client) nên không dùng chung fixture auth_client của file kia."""

    def __init__(self):
        self.store: dict[str, str] = {}

    async def set(self, k, v, ex=None):
        self.store[k] = v

    async def get(self, k):
        return self.store.get(k)

    async def delete(self, k):
        self.store.pop(k, None)


@pytest.mark.asyncio
async def test_forgot_reset_password_full_exploit_chain_blocked_for_added_employee(db_session):
    """Fix 1 (review toàn nhánh sau plan add_employee, 2026-07-27): add_employee tạo
    record password_hash=None + status=active. login() (Task 1) đã chặn record này,
    nhưng forgot_password/reset_password KHÔNG hề đụng tới nên không có guard —
    exploit: CEO thêm 'Duy Linh' kèm email -> Duy Linh tự bấm 'Quên mật khẩu' ->
    forgot_password tìm thấy anh ta (không guard) -> gửi OTP thật -> reset_password
    cho đặt mật khẩu (không guard) -> login() thành công vì giờ password_hash không
    còn None và status vẫn active. Test này đi hết chuỗi thật (add_employee ->
    forgot_password -> reset_password -> login) để chứng minh chuỗi bị chặn dứt
    điểm, không chỉ chặn ở add_employee->login trực tiếp (đã có ở
    test_create_employee.py::test_added_employee_cannot_login)."""
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db_session.add(ceo)
    await db_session.flush()
    await db_session.commit()

    employee = await auth_service.add_employee(
        db_session, actor=ceo, full_name="Duy Linh", email="duy@a.vn")
    assert employee.password_hash is None
    assert employee.status == UserStatus.active

    redis = _FakeRedis()
    await auth_service.forgot_password(db_session, redis, email="duy@a.vn")
    # Guard đúng phải KHÔNG sinh mã — hành vi phải giống hệt email không tồn tại
    # (chống dò tài khoản chỉ-tên qua sự khác biệt giữa 2 trường hợp).
    assert redis.store == {}

    with pytest.raises(HTTPException) as exc:
        await auth_service.reset_password(
            db_session, redis, email="duy@a.vn", code="000000", new_password="newpassword1")
    assert exc.value.status_code == 400
    assert exc.value.detail == "invalid_or_expired_code"

    await db_session.refresh(employee)
    assert employee.password_hash is None  # reset_password không được sửa gì cả

    with pytest.raises(HTTPException) as exc:
        await auth_service.login(db_session, email="duy@a.vn", password="newpassword1",
                                 device_uuid="d", device_name="")
    assert exc.value.status_code == 401


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
