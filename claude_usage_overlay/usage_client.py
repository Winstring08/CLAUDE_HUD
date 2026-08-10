"""사용량 엔드포인트 → UsageSnapshot. HTTP와 도메인의 경계.

파싱 규칙은 좁다. five_hour 키만 있으면 되고, 나머지는 전부 선택이며,
모르는 키는 존재 여부조차 확인하지 않는다. five_hour가 통째로 null이면
0%로 읽고, 객체인데 utilization이 숫자가 아닐 때만 형식 변경으로 본다.

응답에는 tangelo·iguana_necktie·nimbus_quill 같은 코드네임 필드가 섞여 있고
예고 없이 늘어난다. 엄격하게 검증하면 정상 응답을 형식 변경으로 오탐한다.
"""

import json
from datetime import datetime, timezone
from typing import Callable

from . import http_client
from .models import RateLimited, SchemaChanged, Unauthorized, UsageSnapshot

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
BETA_HEADER = "oauth-2025-04-20"
DEFAULT_RETRY_AFTER = 300


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _window_pct(window) -> float | None:
    if not isinstance(window, dict):
        return None
    value = window.get("utilization")
    return float(value) if value is not None else None


def _parse_dt(value) -> datetime | None:
    """못 읽으면 None. 형식 변경으로 취급하지 않는다.

    사용률은 멀쩡한데 시각만 못 읽는 상황이므로, 카운트다운만 포기하고
    숫자는 그대로 보여준다.

    읽히더라도 tz-naive면 UTC로 못박는다. 오버레이는 이 값을 tz-aware
    now와 매초 빼는데, naive가 섞이면 TypeError로 화면이 얼어붙는다.
    tkinter after 콜백 안이라 스택트레이스도 안 남아 진단이 불가능하다.
    """
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def fetch_usage(
    token: str,
    request_fn: Callable = http_client.request,
    now: Callable[[], datetime] = _now,
) -> UsageSnapshot:
    res = request_fn(
        "GET",
        USAGE_URL,
        {"Authorization": f"Bearer {token}", "anthropic-beta": BETA_HEADER},
    )

    if res.status == 401:
        raise Unauthorized("401 — 토큰 갱신이 필요합니다")

    if res.status == 429:
        raw = res.headers.get("retry-after", "")
        try:
            retry_after = int(raw)
        except (TypeError, ValueError):
            retry_after = DEFAULT_RETRY_AFTER
        raise RateLimited(retry_after)

    if res.status != 200:
        raise SchemaChanged(f"예상치 못한 상태 코드 {res.status}")

    try:
        data = json.loads(res.body)
    except json.JSONDecodeError as err:
        raise SchemaChanged(f"JSON이 아닙니다: {err}") from err

    if not isinstance(data, dict) or "five_hour" not in data:
        raise SchemaChanged("five_hour 키가 없습니다")

    five_hour = data["five_hour"]

    if five_hour is None:
        # 값이 없는 창은 통째로 null로 온다 (tangelo·cinder_cove가 그렇다).
        # 숫자가 사라진 게 아니라 쓴 게 없다는 뜻이므로 0%로 읽는다.
        return UsageSnapshot(
            five_hour_pct=0.0,
            resets_at=None,
            seven_day_pct=_window_pct(data.get("seven_day")),
            fetched_at=now(),
        )

    # 객체가 왔으면 utilization은 반드시 숫자여야 한다. 아니면 보여줄 값이 없는 것이다.
    try:
        pct = float(five_hour["utilization"])
    except (KeyError, TypeError, ValueError) as err:
        raise SchemaChanged(f"five_hour.utilization을 읽을 수 없습니다: {err}") from err

    return UsageSnapshot(
        five_hour_pct=pct,
        resets_at=_parse_dt(five_hour.get("resets_at")),
        seven_day_pct=_window_pct(data.get("seven_day")),
        fetched_at=now(),
    )
