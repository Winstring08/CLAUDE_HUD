from datetime import datetime, timedelta, timezone

from claude_usage_overlay.formatting import (
    NO_RESET_TEXT,
    format_age,
    format_countdown,
    format_ring_time,
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


def test_ring_time_is_hours_and_minutes():
    """링 안은 좁아서 `5시간 20분 후 리셋`이 안 들어간다. `5:20`으로 줄인다."""
    assert format_ring_time(NOW + timedelta(hours=5, minutes=20), NOW) == "5:20"


def test_ring_time_does_not_pad_the_hour():
    """자리를 채우는 0은 붙이지 않는다. `05:27`은 시계로 읽히고 남은 시간이
    아니라 리셋 시각처럼 보인다."""
    assert format_ring_time(NOW + timedelta(minutes=27), NOW) == "0:27"


def test_ring_time_pads_the_minute():
    """분은 채운다. `5:3`은 3분인지 30분인지 읽는 사람이 못 가른다."""
    assert format_ring_time(NOW + timedelta(hours=5, minutes=3), NOW) == "5:03"


def test_ring_time_allows_a_two_digit_hour():
    """5시간 창이니 한 자리일 것 같지만 format_countdown의 최장이
    `10시간 14분 후 리셋`이라 코드는 두 자리를 허용한다. 표기 규칙을 따로 두지
    않는다 — 링 안에서는 글자가 작아질 뿐 잘리지 않는다 (스펙 3.3절)."""
    assert format_ring_time(NOW + timedelta(hours=10, minutes=14), NOW) == "10:14"


def test_ring_time_without_a_reset_is_a_dash():
    """사용량 0인 새 창에서는 resets_at이 null로 온다."""
    assert format_ring_time(None, NOW) == NO_RESET_TEXT


def test_ring_time_never_goes_negative():
    """리셋 시각을 지나쳤는데 다음 조회 전이면 음수 초가 나온다."""
    assert format_ring_time(NOW - timedelta(minutes=5), NOW) == "0:00"
