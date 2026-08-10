"""시각 → 한국어 문구. 오버레이는 이 함수들만 호출한다."""

from datetime import datetime


NO_RESET_TEXT = "—"


def format_countdown(resets_at: datetime | None, now: datetime) -> str:
    if resets_at is None:
        return NO_RESET_TEXT
    remaining = int((resets_at - now).total_seconds())
    if remaining <= 0:
        return "곧 리셋"
    hours, minutes = divmod(remaining // 60, 60)
    if hours:
        return f"{hours}시간 {minutes}분 후 리셋"
    return f"{minutes}분 후 리셋"


def format_age(fetched_at: datetime, now: datetime) -> str:
    seconds = int((now - fetched_at).total_seconds())
    if seconds < 60:
        return "방금 갱신됨"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}분 전 갱신"
    return f"{minutes // 60}시간 전 갱신"


def format_stale_detail(fetched_at: datetime, now: datetime) -> str:
    minutes = max(1, int((now - fetched_at).total_seconds()) // 60)
    return f"{minutes}분째 갱신 실패"
