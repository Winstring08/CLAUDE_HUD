"""시각 → 한국어 문구. 오버레이는 이 함수들만 호출한다."""

from datetime import datetime


NO_RESET_TEXT = "—"

# 상태 문구. 폴러가 HudState.detail에 넣고 오버레이와 트레이 툴팁이 그대로 쓴다.
#
# **짧게 유지한다.** 이 문구들이 오버레이 창 폭을 결정하기 때문이다 — 창은
# 가장 긴 문구에서 역산하는데, 드물게 뜨는 안내 하나가 길면 평소 화면에
# 빈 공간만 남는다. 실측으로 "Claude Code를 한 번 실행하세요"가 228px,
# "호출 한도 — 잠시 후 재시도"가 202px을 요구해 창이 240px까지 커져 있었고,
# 평소 표시(최대 169px)에는 71px이 늘 비었다.
LOADING_TEXT = "불러오는 중"
NO_DATA_TEXT = "데이터 없음"
RATE_LIMITED_TEXT = "호출 한도 초과"
SCHEMA_ERROR_TEXT = "데이터 형식이 바뀜"
AUTH_RETRY_TEXT = "인증 재시도 중"


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
