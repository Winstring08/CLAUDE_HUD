"""도메인 타입과 예외. 다른 모든 모듈이 이 파일을 참조한다."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Status(Enum):
    """UI가 보는 유일한 상태 값."""

    OK = "ok"
    STALE = "stale"
    RATE_LIMITED = "rate_limited"
    RELOGIN = "relogin"
    SCHEMA_ERROR = "schema_error"


@dataclass(frozen=True)
class UsageSnapshot:
    five_hour_pct: float
    resets_at: datetime | None   # 사용량 0인 새 창에서는 null로 온다
    seven_day_pct: float | None
    fetched_at: datetime


@dataclass(frozen=True)
class HudState:
    """폴러가 만들고 UI가 소비하는 값. UI는 이것만 보면 된다."""

    status: Status
    snapshot: UsageSnapshot | None
    detail: str


class ReloginRequired(Exception):
    """토큰을 쓸 수 없는 상태. 우리는 갱신하지 않으므로 사용자가 조치해야 한다.

    두 가지 원인을 문구로 구분한다.
      accessToken만 만료  → "Claude Code를 한 번 실행하세요"
      그 외(refreshToken 만료·파일 없음·손상) → "claude auth login"
    """


class RateLimited(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__(f"rate limited, retry after {retry_after}s")
        self.retry_after = retry_after


class Unauthorized(Exception):
    """401. 토큰을 갱신하면 회복될 수 있다."""


class SchemaChanged(Exception):
    """응답 형식이 예상과 다르다. 숫자를 지어내지 않고 이 예외를 던진다."""
