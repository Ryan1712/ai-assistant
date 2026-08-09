"""Finding #19 (audit 2026-07-26, re-verify 2026-08-08, MED): authorize_ws
chỉ decode token + check workspace/user khớp conversation, KHÔNG check
UserStatus.locked -- user bị khóa vẫn mở được WS mới nếu JWT cũ còn hạn
(so sánh deps.py::get_current_user CÓ check locked cho REST)."""
import pytest

from app import security
from app.api.ws import WebSocketAuthError, authorize_ws
from app.models import Conversation, Role, User, UserStatus, Workspace


async def _world(db, status=UserStatus.active):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True, status=status)
    db.add(ceo)
    await db.flush()
    conv = Conversation(workspace_id=ws.id, user_id=ceo.id)
    db.add(conv)
    await db.flush()
    await db.commit()
    return ws, ceo, conv


@pytest.mark.asyncio
async def test_ws_tu_choi_user_bi_khoa(db_session):
    ws, ceo, conv = await _world(db_session, status=UserStatus.locked)
    token = security.create_access_token(user_id=str(ceo.id), workspace_id=str(ws.id),
                                         role=ceo.role.value)
    with pytest.raises(WebSocketAuthError):
        await authorize_ws(db_session, token, conv.id)


@pytest.mark.asyncio
async def test_ws_chap_nhan_user_active(db_session):
    ws, ceo, conv = await _world(db_session, status=UserStatus.active)
    token = security.create_access_token(user_id=str(ceo.id), workspace_id=str(ws.id),
                                         role=ceo.role.value)
    result = await authorize_ws(db_session, token, conv.id)
    assert result.id == conv.id
