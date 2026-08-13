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


def format_ring_time(resets_at: datetime | None, now: datetime) -> str:
    """링 안에 넣는 남은 시간. `5:20`(시:분).

    format_countdown과 따로 두는 이유는 들어갈 자리가 다르기 때문이다. 링 안쪽은
    32px뿐이라 `5시간 20분 후 리셋`이 들어가지 않는다.

    **시에는 자리를 채우는 0을 붙이지 않는다.** `05:27`은 시계로 읽혀서 남은
    시간이 아니라 리셋 시각처럼 보인다. 분은 채운다 — `5:3`은 3분인지 30분인지
    읽는 사람이 못 가른다.

    **시가 한 자리라고 가정하지 않는다.** 5시간 창이니 그럴 것 같지만
    format_countdown의 최장이 "10시간 14분 후 리셋"이라 코드는 두 자리를 허용한다.
    링 안에서는 글자가 작아질 뿐 잘리지 않는다 (overlay._ring_font).
    """
    if resets_at is None:
        return NO_RESET_TEXT
    remaining = max(0, int((resets_at - now).total_seconds()))
    hours, minutes = divmod(remaining // 60, 60)
    return f"{hours}:{minutes:02d}"


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
