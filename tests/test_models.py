from datetime import datetime, timezone

from claude_usage_overlay.models import (
    HudState,
    RateLimited,
    Status,
    UsageSnapshot,
)


def test_snapshot_holds_five_hour_values():
    snap = UsageSnapshot(
        five_hour_pct=23.0,
        resets_at=datetime(2026, 8, 10, 5, 40, tzinfo=timezone.utc),
        seven_day_pct=15.0,
        fetched_at=datetime(2026, 8, 10, 3, 25, tzinfo=timezone.utc),
    )
    assert snap.five_hour_pct == 23.0
    assert snap.seven_day_pct == 15.0


def test_snapshot_allows_missing_seven_day():
    snap = UsageSnapshot(
        five_hour_pct=23.0,
        resets_at=datetime(2026, 8, 10, 5, 40, tzinfo=timezone.utc),
        seven_day_pct=None,
        fetched_at=datetime(2026, 8, 10, 3, 25, tzinfo=timezone.utc),
    )
    assert snap.seven_day_pct is None


def test_snapshot_allows_missing_resets_at():
    """사용량 0인 새 창에서는 resets_at이 null로 온다 (스펙 3.1)."""
    snap = UsageSnapshot(
        five_hour_pct=0.0,
        resets_at=None,
        seven_day_pct=None,
        fetched_at=datetime(2026, 8, 10, 3, 25, tzinfo=timezone.utc),
    )
    assert snap.resets_at is None
    assert snap.five_hour_pct == 0.0


def test_hud_state_can_carry_no_snapshot():
    state = HudState(status=Status.RELOGIN, snapshot=None, detail="재로그인 필요")
    assert state.snapshot is None
    assert state.status is Status.RELOGIN


def test_rate_limited_carries_retry_after():
    err = RateLimited(retry_after=287)
    assert err.retry_after == 287
