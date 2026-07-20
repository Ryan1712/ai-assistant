"""Phase 1: render per-actor — QUAN TRỌNG NHẤT là test không lộ vượt quyền."""
from datetime import datetime, timezone

from app.services.snapshot_service import render_for_actor

NOW = datetime(2026, 7, 20, 3, 0, tzinfo=timezone.utc)

DATA = {
    "built_at": "2026-07-20T03:00:00+00:00",
    "projects": [
        {"id": "p1", "name": "Marketing Q3", "status": "active", "deadline": None,
         "task_total": 3, "task_open": 2, "task_blocked": 1, "task_overdue": 1,
         "task_done": 1, "percent_avg": 47},
        {"id": "p2", "name": "Dự án mật", "status": "active", "deadline": None,
         "task_total": 1, "task_open": 1, "task_blocked": 0, "task_overdue": 0,
         "task_done": 0, "percent_avg": 0},
    ],
    "users": [
        {"id": "u-ceo", "full_name": "Sếp", "role": "ceo", "manager_name": None,
         "open_count": 0, "overdue_count": 0, "last_update_at": None, "doing": []},
        {"id": "u-duy", "full_name": "Duy Phạm", "role": "employee",
         "manager_name": "Hà Trần", "open_count": 2, "overdue_count": 1,
         "last_update_at": "2026-07-20T01:00:00+00:00",
         "doing": [{"task_id": "t1", "title": "Landing page",
                    "project_name": "Marketing Q3", "percent": 40,
                    "deadline": "2026-07-23T03:00:00+00:00"}]},
        {"id": "u-nam", "full_name": "Nam Nguyễn", "role": "employee",
         "manager_name": "Hà Trần", "open_count": 1, "overdue_count": 0,
         "last_update_at": None,
         "doing": [{"task_id": "t9", "title": "Việc bí mật",
                    "project_name": "Dự án mật", "percent": 10, "deadline": None}]},
    ],
    "due_today": [{"task_id": "t4", "title": "Họp khách",
                   "project_name": "Marketing Q3", "assignees": ["Hà Trần"]}],
    "overdue": [{"task_id": "t2", "title": "Báo cáo thuế",
                 "project_name": "Marketing Q3", "assignees": ["Duy Phạm"],
                 "deadline": "2026-07-18T03:00:00+00:00"}],
    "updates_24h": [{"task_id": "t1", "task_title": "Landing page",
                     "author": "Duy Phạm", "content": "đã xong hero section",
                     "percent": 40, "at": "2026-07-20T01:00:00+00:00"}],
}


def test_ceo_thay_du_va_dung_format():
    text = render_for_actor(DATA, "u-ceo",
                            visible_projects={"p1", "p2"},
                            visible_tasks={"t1", "t2", "t4", "t9"},
                            visible_users={"u-ceo", "u-duy", "u-nam"}, now=NOW)
    assert text.startswith("# Trạng thái công ty")
    assert "## Dự án" in text and "## Nhân sự & khối lượng" in text and "## Hôm nay" in text
    assert "Marketing Q3" in text and "Dự án mật" in text
    assert "Duy Phạm" in text and "Landing page" in text and "40%" in text
    assert "Họp khách" in text and "Báo cáo thuế" in text
    assert "đã xong hero section" in text


def test_employee_khong_lo_du_lieu_nguoi_khac():
    # Duy chỉ thấy: project p1, task t1/t2 (của mình), user chính mình
    text = render_for_actor(DATA, "u-duy",
                            visible_projects={"p1"}, visible_tasks={"t1", "t2"},
                            visible_users={"u-duy"}, now=NOW)
    assert "Dự án mật" not in text
    assert "Việc bí mật" not in text
    assert "Nam Nguyễn" not in text
    assert "Họp khách" not in text          # t4 không thuộc visible_tasks
    assert "Landing page" in text            # việc của mình vẫn thấy
    assert "Báo cáo thuế" in text            # quá hạn của mình vẫn thấy


def test_manager_thay_nhanh_minh():
    # Hà (giả sử) thấy p1, t1/t2/t4, và user Duy (report) + chính mình (không có
    # trong DATA users thì bỏ qua im lặng — data build trước khi Hà join chẳng hạn)
    text = render_for_actor(DATA, "u-ha",
                            visible_projects={"p1"}, visible_tasks={"t1", "t2", "t4"},
                            visible_users={"u-ha", "u-duy"}, now=NOW)
    assert "Duy Phạm" in text and "Nam Nguyễn" not in text
    assert "Họp khách" in text and "Việc bí mật" not in text


def test_du_lieu_rong_van_co_header():
    empty = {"built_at": DATA["built_at"], "projects": [], "users": [],
             "due_today": [], "overdue": [], "updates_24h": []}
    text = render_for_actor(empty, "u-x", visible_projects=set(),
                            visible_tasks=set(), visible_users=set(), now=NOW)
    assert text.startswith("# Trạng thái công ty")
    assert "chưa có dữ liệu" in text


def test_cap_do_dai():
    big = dict(DATA)
    big["updates_24h"] = [{"task_id": "t1", "task_title": "Landing page",
                           "author": "Duy Phạm", "content": "x" * 500,
                           "percent": 1, "at": DATA["built_at"]}] * 50
    text = render_for_actor(big, "u-ceo", visible_projects={"p1", "p2"},
                            visible_tasks={"t1", "t2", "t4", "t9"},
                            visible_users={"u-ceo", "u-duy", "u-nam"}, now=NOW)
    assert len(text) <= 8100   # 8000 + ghi chú cắt
