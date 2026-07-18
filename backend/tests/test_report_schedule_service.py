from datetime import datetime, timezone

from app.services.report_schedule_service import compute_next_run

MON_10AM = datetime(2026, 7, 13, 10, 0, tzinfo=timezone.utc)  # thứ Hai 13/07/2026, 17:00 VN


def test_daily_time_already_passed_today_rolls_to_tomorrow():
    # 8h VN < 17h VN (hiện tại) → đã qua → 8h VN ngày mai (14/7) = 01:00 UTC
    assert compute_next_run(MON_10AM, None, 8, 0) == datetime(2026, 7, 14, 1, 0,
                                                               tzinfo=timezone.utc)


def test_daily_time_not_yet_passed_today_stays_today():
    # 14h VN cũng < 17h VN (hiện tại) → đã qua trong ngày VN → rolls sang ngày mai
    # (khác UTC cũ: 14h UTC > 10h UTC "còn trong ngày" — nhưng theo giờ VN đã trôi qua)
    # 14h VN ngày mai (14/7) = 07:00 UTC
    assert compute_next_run(MON_10AM, None, 14, 0) == datetime(2026, 7, 14, 7, 0,
                                                                tzinfo=timezone.utc)


def test_weekly_same_weekday_already_passed_rolls_to_next_week():
    # weekday=0 (thứ Hai) 8h VN — hôm nay (VN) là thứ Hai nhưng 8h VN đã qua → tuần sau
    # thứ Hai 20/7 08:00 VN = 01:00 UTC
    assert compute_next_run(MON_10AM, 0, 8, 0) == datetime(2026, 7, 20, 1, 0,
                                                            tzinfo=timezone.utc)


def test_weekly_future_weekday_this_week():
    # weekday=2 (thứ Tư) 8h VN — còn trong tuần này; thứ Tư 15/7 08:00 VN = 01:00 UTC
    assert compute_next_run(MON_10AM, 2, 8, 0) == datetime(2026, 7, 15, 1, 0,
                                                            tzinfo=timezone.utc)


def test_compute_next_run_hieu_gio_vn():
    # 02:00 UTC = 09:00 VN. Đặt 8h sáng → đã qua hôm nay (VN) → 8h VN ngày mai = 01:00 UTC ngày mai
    after = datetime(2026, 7, 19, 2, 0, tzinfo=timezone.utc)
    assert compute_next_run(after, weekday=None, hour=8, minute=0) == \
        datetime(2026, 7, 20, 1, 0, tzinfo=timezone.utc)


def test_compute_next_run_trong_ngay_vn():
    # 02:00 UTC = 09:00 VN. Đặt 10:30 VN → còn trong hôm nay = 03:30 UTC
    after = datetime(2026, 7, 19, 2, 0, tzinfo=timezone.utc)
    assert compute_next_run(after, weekday=None, hour=10, minute=30) == \
        datetime(2026, 7, 19, 3, 30, tzinfo=timezone.utc)


def test_compute_next_run_weekday_theo_vn():
    # 2026-07-19 18:00 UTC = Thứ Hai 01:00 VN (20/7). Đặt thứ Hai (0) 08:00 VN
    # → ngay hôm đó theo VN: 2026-07-20 01:00 UTC
    after = datetime(2026, 7, 19, 18, 0, tzinfo=timezone.utc)
    assert compute_next_run(after, weekday=0, hour=8, minute=0) == \
        datetime(2026, 7, 20, 1, 0, tzinfo=timezone.utc)
