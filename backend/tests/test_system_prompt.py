import uuid
from datetime import datetime, timezone

from app.agent.loop import _build_system_prompt
from app.models import Role, User


def _actor(role=Role.employee) -> User:
    return User(id=uuid.uuid4(), workspace_id=uuid.uuid4(), email="a@b.c",
                password_hash="x", full_name="Nam Test", role=role)


def test_prompt_gio_viet_nam():
    # 2026-07-19 18:30 UTC = 2026-07-20 01:30 VN (Thứ Hai)
    now = datetime(2026, 7, 19, 18, 30, tzinfo=timezone.utc)
    prompt = _build_system_prompt(_actor(), now=now)
    assert "2026-07-20" in prompt          # ngày theo VN, không phải UTC
    assert "01:30" in prompt               # có giờ, không chỉ ngày
    assert "Việt Nam" in prompt
    assert "Thứ Hai" in prompt


def test_prompt_co_role_va_huong_dan():
    prompt = _build_system_prompt(_actor(), now=datetime(2026, 7, 19, 4, 0, tzinfo=timezone.utc))
    assert "employee" in prompt
    assert "tiếng Việt" in prompt          # chỉ dẫn ngôn ngữ tường minh
    assert "use_skill" in prompt           # gợi ý dùng skill
    assert "CEO" in prompt                 # nêu ranh giới quyền chính
