from datetime import datetime, timezone

from app.services.report_schedule_service import compute_next_run

MON_10AM = datetime(2026, 7, 13, 10, 0, tzinfo=timezone.utc)  # thứ Hai 13/07/2026


def test_daily_time_already_passed_today_rolls_to_tomorrow():
    assert compute_next_run(MON_10AM, None, 8, 0) == datetime(2026, 7, 14, 8, 0,
                                                               tzinfo=timezone.utc)


def test_daily_time_not_yet_passed_today_stays_today():
    assert compute_next_run(MON_10AM, None, 14, 0) == datetime(2026, 7, 13, 14, 0,
                                                                tzinfo=timezone.utc)


def test_weekly_same_weekday_already_passed_rolls_to_next_week():
    # weekday=0 (thứ Hai) 8h — hôm nay là thứ Hai nhưng 8h đã qua → tuần sau
    assert compute_next_run(MON_10AM, 0, 8, 0) == datetime(2026, 7, 20, 8, 0,
                                                            tzinfo=timezone.utc)


def test_weekly_future_weekday_this_week():
    # weekday=2 (thứ Tư) 8h — còn trong tuần này
    assert compute_next_run(MON_10AM, 2, 8, 0) == datetime(2026, 7, 15, 8, 0,
                                                            tzinfo=timezone.utc)
