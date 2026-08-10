"""주기 조회, 백오프, 상태 판정.

로직은 전부 step() 안에 있다. start()는 step()을 반복하는 껍데기라
스레드 없이 step()만 테스트하면 된다.
"""

import threading
from datetime import datetime, timedelta, timezone
from typing import Callable

from .config import Config
from .formatting import (
    AUTH_RETRY_TEXT,
    LOADING_TEXT,
    NO_DATA_TEXT,
    RATE_LIMITED_TEXT,
    SCHEMA_ERROR_TEXT,
    format_stale_detail,
)
from .models import (
    HudState,
    RateLimited,
    ReloginRequired,
    SchemaChanged,
    Status,
    Unauthorized,
    UsageSnapshot,
)
from .usage_client import fetch_usage

MAX_BACKOFF_SECONDS = 1800
RATE_LIMIT_PADDING = 5
MAX_UNAUTHORIZED = 3   # 이 횟수만큼 연속 401이면 경합이 아니라 인증 문제다


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Poller:
    def __init__(
        self,
        store,
        config: Config,
        fetch_fn: Callable = fetch_usage,
        now: Callable[[], datetime] = _now,
    ) -> None:
        self._store = store
        self._config = config
        self._fetch = fetch_fn
        self._now = now

        self._lock = threading.Lock()
        self._state = HudState(Status.STALE, None, LOADING_TEXT)
        self._last_snapshot: UsageSnapshot | None = None
        self._failures = 0
        self._unauthorized = 0
        self._blocked_until: datetime | None = None   # 429 벌칙이 끝나는 시각

        self._wake = threading.Event()
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None

    # --- 공개 인터페이스 -------------------------------------------------

    def state(self) -> HudState:
        with self._lock:
            return self._state

    def step(self) -> int:
        """한 번 조회하고 상태를 갱신한 뒤, 다음 호출까지 기다릴 초를 반환한다."""
        try:
            token = self._store.get_access_token()
            snapshot = self._fetch(token)
        except RateLimited as err:
            delay = err.retry_after + RATE_LIMIT_PADDING
            # request_now()가 이 구간을 깨우지 못하게 막는다 (스펙 8장).
            self._blocked_until = self._now() + timedelta(seconds=delay)
            self._set(Status.RATE_LIMITED, self._last_snapshot, RATE_LIMITED_TEXT)
            return delay
        except Unauthorized:
            return self._handle_unauthorized()
        except ReloginRequired as err:
            # 무엇을 해야 하는지는 credentials가 안다. 문구를 그대로 넘긴다.
            self._set(Status.RELOGIN, None, str(err))
            # 백오프를 태우지 않는다. 자격증명 확인은 로컬 파일 읽기라 비용이 0이고,
            # 늦출수록 사용자가 Claude Code를 실행해 고쳐놓은 것을 늦게 알아챌
            # 뿐이다. 30분까지 늘리면 README의 "한 번 실행하면 낫는다"가 거짓이 된다.
            return self._config.poll_seconds
        except SchemaChanged:
            self._set(Status.SCHEMA_ERROR, None, SCHEMA_ERROR_TEXT)
            return self._backoff()
        except Exception:  # 네트워크 오류 등
            return self._handle_transient()

        self._failures = 0
        self._unauthorized = 0
        self._last_snapshot = snapshot
        self._set(Status.OK, snapshot, "")
        return self._config.poll_seconds

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopping.set()
        self._wake.set()

    def request_now(self) -> None:
        """트레이의 '지금 갱신' 메뉴가 호출한다.

        429 벌칙 중에는 아무 일도 하지 않는다. 스펙 8장은 retry-after까지
        호출하지 않기로 정했고, 트레이 메뉴가 유일한 조작 수단이라 사용자는
        답답할 때 이 버튼을 누른다. 여기서 깨우면 429가 또 나고 벌칙만 길어진다.
        화면에는 이미 "호출 한도 초과"가 떠 있다.
        """
        if self._blocked_until is not None and self._now() < self._blocked_until:
            return
        self._wake.set()

    # --- 내부 ------------------------------------------------------------

    def _loop(self) -> None:
        while not self._stopping.is_set():
            delay = self.step()
            self._wake.wait(timeout=delay)
            self._wake.clear()

    def _set(self, status: Status, snapshot: UsageSnapshot | None, detail: str) -> None:
        with self._lock:
            self._state = HudState(status, snapshot, detail)

    def _backoff(self) -> int:
        self._failures += 1
        delay = self._config.poll_seconds * (2 ** (self._failures - 1))
        return min(delay, MAX_BACKOFF_SECONDS)

    def _handle_unauthorized(self) -> int:
        """401을 즉시 포기하지 않는 이유.

        만료 직전 토큰으로 호출한 순간 Claude Code가 파일을 갱신하면 401이 난다.
        정상 경합이고, CredentialStore가 매번 파일을 다시 읽으므로 다음 틱이면
        저절로 낫는다. 세 번을 넘기면 그건 경합이 아니다.
        """
        self._unauthorized += 1
        if self._unauthorized >= MAX_UNAUTHORIZED:
            self._set(Status.RELOGIN, None, "인증 거부됨 — claude auth login")
            # 여기서도 백오프하지 않는다. ReloginRequired와 회복 경로가 같으므로
            # (사용자가 조치하면 다음 틱에 낫는다) 지연도 같아야 한다.
            return self._config.poll_seconds

        self._mark_stale(AUTH_RETRY_TEXT)
        # 백오프를 태우지 않는다. 이 401은 경합이고 회복은 다음 틱에 파일을 다시
        # 읽으면 끝난다. 지연을 늘리면 5분이면 나을 것이 10분, 20분이 되고 3회를
        # 채우는 데 35분이 걸린다. _failures도 건드리지 않는다 — 인증 경합과
        # 네트워크 단절은 다른 사건이라 카운터를 공유하면 안 된다.
        return self._config.poll_seconds

    def _handle_transient(self) -> int:
        self._mark_stale()
        return self._backoff()

    def _mark_stale(self, detail: str | None = None) -> None:
        if self._last_snapshot is None:
            self._set(Status.STALE, None, detail or NO_DATA_TEXT)
            return
        detail = detail or format_stale_detail(self._last_snapshot.fetched_at, self._now())
        self._set(Status.STALE, self._last_snapshot, detail)
