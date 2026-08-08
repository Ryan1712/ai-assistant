"""Finding #15 (audit 2026-07-26, re-verify 2026-08-08, HIGH): reset_password
không rate-limit OTP 6 số (brute-forceable trong TTL 15') và không revoke
RefreshToken sau khi đổi mật khẩu thành công (session-fixation nếu tài
khoản bị chiếm, chủ tài khoản reset nhưng token cũ của kẻ tấn công vẫn
sống)."""
import datetime as dt

import pytest
from fastapi import HTTPException

from app.models import Role, User, Workspace
from app.services import auth_service


class _FakeRedis:
    """Redis in-memory tối thiểu cho test — cùng interface với
    tests/test_password_reset.py::_FakeRedis / tests/test_auth_service_login.py::_FakeRedis,
    khai báo thêm incr/expire (finding #15 cần counter rate-limit, 2 file kia không cần)."""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.ttl: dict[str, int] = {}

    async def set(self, k, v, ex=None):
        self.store[k] = v

    async def get(self, k):
        return self.store.get(k)

    async def delete(self, k):
        self.store.pop(k, None)
        self.ttl.pop(k, None)

    async def incr(self, k):
        cur = int(self.store.get(k, "0")) + 1
        self.store[k] = str(cur)
        return cur

    async def expire(self, k, seconds):
        self.ttl[k] = seconds


async def _seed_user_with_email(db, email):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    user = User(workspace_id=ws.id, email=email, password_hash="x", full_name="U",
               role=Role.ceo, is_root=True)
    db.add(user)
    await db.commit()
    return ws, user


def _get_last_otp_from_mock_email(email):
    """Lấy OTP thật cuối cùng đã gửi cho `email` từ MockEmailClient.sent (dev
    email_mock=True — mặc định trong test). forgot_password() ghi body dạng
    'Mã đặt lại mật khẩu của bạn là {code}. ...' — parse số 6 chữ số ngay sau
    'là '."""
    from app.services.email_service import mock_email_client
    for entry in reversed(mock_email_client.sent):
        if entry["to"] == email:
            body = entry["body"]
            marker = "là "
            idx = body.index(marker) + len(marker)
            return body[idx:idx + 6]
    raise AssertionError(f"khong tim thay email da gui cho {email}")


@pytest.mark.asyncio
async def test_reset_password_chan_sau_qua_nhieu_lan_sai_otp(db_session):
    redis = _FakeRedis()
    ws, user = await _seed_user_with_email(db_session, "reset1@a.vn")
    await auth_service.forgot_password(db_session, redis, email="reset1@a.vn")

    for _ in range(5):
        with pytest.raises(HTTPException) as exc:
            await auth_service.reset_password(
                db_session, redis, email="reset1@a.vn",
                code="000000", new_password="newpass123")
        assert exc.value.status_code == 400  # sai OTP bình thường, chưa chạm rate-limit

    with pytest.raises(HTTPException) as exc:
        await auth_service.reset_password(
            db_session, redis, email="reset1@a.vn",
            code="000000", new_password="newpass123")
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_reset_password_revoke_refresh_token_cu(db_session):
    from app.models import RefreshToken

    redis = _FakeRedis()
    ws, user = await _seed_user_with_email(db_session, "reset2@a.vn")
    old_token = RefreshToken(workspace_id=ws.id, user_id=user.id, token_hash="x",
                             expires_at=dt.datetime.now(dt.timezone.utc)
                             + dt.timedelta(days=30))
    db_session.add(old_token)
    await db_session.commit()

    await auth_service.forgot_password(db_session, redis, email="reset2@a.vn")
    code = _get_last_otp_from_mock_email("reset2@a.vn")
    await auth_service.reset_password(
        db_session, redis, email="reset2@a.vn", code=code,
        new_password="newpass123")

    await db_session.refresh(old_token)
    assert old_token.revoked_at is not None
