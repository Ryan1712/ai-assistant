import uuid
from datetime import datetime, timedelta, timezone

from app.agent.loop import _build_system_prompt
from app.models import Role, User


def _fake_actor():
    return User(id=uuid.uuid4(), email="c@a.vn", password_hash="x", full_name="C",
               role=Role.ceo, is_root=True, workspace_id=uuid.uuid4())


def test_static_prompt_contains_3_tier_rule_and_resolver_guidance():
    prompt = _build_system_prompt(_fake_actor())
    assert "propose_actions" in prompt
    assert "resolve_person" in prompt
    assert "resolve_task" in prompt


def test_static_prompt_structurally_stable_across_different_now():
    actor = _fake_actor()
    now1 = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)
    now2 = now1 + timedelta(days=3, hours=5)
    p1 = _build_system_prompt(actor, now1)
    p2 = _build_system_prompt(actor, now2)
    # Chỉ khác nhau ở dòng ngày/giờ VN — cắt dòng đó ra rồi so phần còn lại phải giống hệt
    # (không phá cache prompt vì đổi giờ gọi).
    lines1 = [ln for ln in p1.split("\n") if "giờ Việt Nam" not in ln]
    lines2 = [ln for ln in p2.split("\n") if "giờ Việt Nam" not in ln]
    assert lines1 == lines2
