from datetime import datetime, timedelta, timezone

from claude_usage_overlay.formatting import (
    format_age,
    format_countdown,
    format_stale_detail,
)

NOW = datetime(2026, 8, 10, 3, 25, tzinfo=timezone.utc)


def test_countdown_over_an_hour_shows_hours_and_minutes():
    assert format_countdown(NOW + timedelta(hours=2, minutes=14), NOW) == "2시간 14분 후 리셋"


def test_countdown_under_an_hour_shows_minutes_only():
    assert format_countdown(NOW + timedelta(minutes=18), NOW) == "18분 후 리셋"


def test_countdown_in_the_past_says_soon():
    assert format_countdown(NOW - timedelta(minutes=1), NOW) == "곧 리셋"


def test_countdown_without_resets_at_is_a_dash():
    """응답에 resets_at이 없어도 사용률은 멀쩡하다. 카운트다운만 비운다."""
    assert format_countdown(None, NOW) == "—"


def test_age_under_a_minute_says_just_now():
    assert format_age(NOW - timedelta(seconds=30), NOW) == "방금 갱신됨"


def test_age_in_minutes():
    assert format_age(NOW - timedelta(minutes=14), NOW) == "14분 전 갱신"


def test_age_in_hours():
    assert format_age(NOW - timedelta(hours=3), NOW) == "3시간 전 갱신"


def test_stale_detail_counts_minutes_since_last_success():
    assert format_stale_detail(NOW - timedelta(minutes=14), NOW) == "14분째 갱신 실패"
