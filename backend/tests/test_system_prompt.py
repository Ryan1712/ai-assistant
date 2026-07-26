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


def test_prompt_nguoi_chua_co_trong_danh_sach_nhan_vien():
    """Cùng vấn đề 2026-07-26 (vế prompt): khi nhắc tới người không có trong danh
    bạ, AI phải nói 'X chưa có trong danh sách nhân viên' + đề nghị thêm mới —
    không hỏi 'có tài khoản trong hệ thống chưa'."""
    prompt = _build_system_prompt(_actor(), now=datetime(2026, 7, 19, 4, 0, tzinfo=timezone.utc))
    assert "chưa có trong danh sách nhân viên" in prompt
    assert "có tài khoản trong hệ thống chưa" in prompt  # nêu đích danh câu bị cấm


def test_prompt_cam_lo_ten_tool_noi_bo():
    """Vấn đề CEO báo 2026-07-26: AI viết thẳng 'create_directive', 'assign_task'
    trong câu trả lời — chi tiết code không được hiển thị cho người dùng. Prompt
    phải có quy tắc tường minh: mô tả hành động bằng tiếng Việt tự nhiên, không
    nhắc tên tool."""
    prompt = _build_system_prompt(_actor(), now=datetime(2026, 7, 19, 4, 0, tzinfo=timezone.utc))
    assert "chi tiết kỹ thuật nội bộ" in prompt
    assert "không viết tên tool" in prompt
