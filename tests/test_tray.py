from datetime import datetime, timedelta, timezone

from claude_usage_overlay.models import HudState, Status, UsageSnapshot
from claude_usage_overlay.tray import TOOLTIP_LIMIT, _tooltip, icon_key

NOW = datetime(2026, 8, 10, 3, 25, tzinfo=timezone.utc)


def state(status=Status.OK, pct=23.0, seven=15.0):
    return HudState(status, UsageSnapshot(pct, NOW + timedelta(hours=2), seven, NOW), "")


def test_icon_key_ignores_sub_percent_drift():
    """23.0%와 23.4%는 같은 그림이다. 다시 그릴 이유가 없다."""
    assert icon_key(state(pct=23.0)) == icon_key(state(pct=23.4))


def test_icon_key_changes_when_the_drawn_digit_changes():
    assert icon_key(state(pct=23.0)) != icon_key(state(pct=24.0))


def test_icon_key_changes_with_status():
    """흐림 여부가 바뀌면 같은 숫자라도 다시 그려야 한다."""
    assert icon_key(state(Status.OK)) != icon_key(state(Status.STALE))


def test_icon_key_handles_a_missing_snapshot():
    assert icon_key(HudState(Status.RELOGIN, None, "재로그인 필요")) == (Status.RELOGIN, None)


def test_tooltip_has_both_windows():
    text = _tooltip(state())
    assert "5시간 창" in text and "23%" in text
    assert "7일 창" in text and "15%" in text


def test_tooltip_omits_seven_day_when_missing():
    assert "7일 창" not in _tooltip(state(seven=None))


def test_tooltip_without_a_snapshot_shows_the_detail():
    """RELOGIN·SCHEMA_ERROR·첫 조회 전이 모두 여기로 온다."""
    text = _tooltip(HudState(Status.RELOGIN, None, "재로그인 필요 — claude auth login"))
    assert "claude auth login" in text


def test_tooltip_never_exceeds_the_win32_buffer():
    """szTip은 128 wchar 고정이다. 넘기면 pystray가 ValueError를 던지고,
    그게 메인 스레드의 pump() 안에서 터져 갱신 루프가 통째로 멈춘다."""
    long_detail = "재로그인 필요 — " + "가" * 300
    for state in (
        HudState(Status.RELOGIN, None, long_detail),
        HudState(Status.STALE, UsageSnapshot(23.0, NOW, 15.0, NOW), long_detail),
    ):
        assert len(_tooltip(state)) <= TOOLTIP_LIMIT
