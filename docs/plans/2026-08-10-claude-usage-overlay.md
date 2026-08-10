# Claude Usage Overlay Implementation Plan

> **For agentic workers:** This plan is the complete task specification. Read it once, then implement it end to end. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Claude 사용량(5시간 창)을 Windows 화면에 항상 띄우는 상주 프로그램을 만든다.

**Architecture:** 백그라운드 스레드가 5분마다 Anthropic OAuth 사용량 엔드포인트를 조회해 하나의 `HudState`로 환산하고, 메인 스레드의 tkinter 오버레이와 pystray 트레이 아이콘이 그 상태만 보고 그린다. HTTP·자격증명·표시 로직은 각각 독립 모듈로 분리해 UI 없이 단위 테스트한다.

**Tech Stack:** Python 3.12, tkinter 8.6(표준 라이브러리), pystray, pillow, urllib(표준 라이브러리), pytest(개발 전용)

## Global Constraints

- Python 3.12 전용. `str | None` 등 3.10+ 문법을 쓴다.
- **Windows 전용.** macOS/Linux 지원은 범위 밖이다.
- **런타임 외부 의존성은 `pystray`와 `pillow` 둘뿐이다.** HTTP는 표준 라이브러리 `urllib`로 처리한다. `requests`를 추가하지 않는다.
- 자격증명 파일: `%USERPROFILE%\.claude\.credentials.json`, 최상위 키 `claudeAiOauth`
- 사용량 조회: `GET https://api.anthropic.com/api/oauth/usage`, 헤더 `Authorization: Bearer <token>` + `anthropic-beta: oauth-2025-04-20`
- 토큰 갱신: `POST https://console.anthropic.com/v1/oauth/token`, 바디 `{"grant_type":"refresh_token","refresh_token":...,"client_id":"9d1c250a-e61b-44d9-88ed-5944d1962f5e"}`
- 폴링 주기 기본값 300초. 429 응답의 `retry-after` 헤더를 반드시 존중한다.
- accessToken 만료 **30분 전**에 갱신한다. 갱신 응답의 `refresh_token`은 **매번 새 값으로 회전하므로 반드시 저장한다.**
- 경고 임계값: 70% 주의(노랑 `#f6c177`) / 90% 위험(빨강 `#ff8f8f`) / 그 미만 정상(초록 `#63e6be`)
- 트레이 아이콘 크기는 런타임에 `GetSystemMetrics(SM_CXSMICON)`로 조회한다. 배율 100%에서 16px, 150%에서 24px이다. 어떤 크기로도 그려져야 한다.
- **드라이브 문자를 하드코딩하지 않는다.** 윈도우 경로는 `%WINDIR%`·`%USERPROFILE%`·`%APPDATA%` 환경변수로 조립한다. 이 프로그램은 특정 PC가 아니라 임의의 윈도우 사용자 환경에서 동작해야 한다.
- 사용자에게 보이는 모든 문구는 한국어로 쓴다.
- **데이터가 없거나 형식이 바뀌면 숫자를 지어내지 않는다.** 상태를 그대로 표시한다.

---

## File Structure

```
claude_usage_overlay/
  __init__.py
  __main__.py         진입점. 설정 로드 → 폴러 기동 → 트레이/오버레이 연결
  models.py           도메인 타입과 예외. 다른 모든 모듈이 참조한다
  http_client.py      urllib 어댑터. 4xx/5xx도 예외 없이 반환한다
  config.py           설정 파일 로드/저장
  theme.py            사용률 → 색 (순수 함수)
  formatting.py       시각 → 한국어 문구 (순수 함수)
  credentials.py      토큰 수명 관리. 가장 위험한 모듈
  usage_client.py     사용량 엔드포인트 → UsageSnapshot
  poller.py           주기 조회, 백오프, 상태 판정
  winmetrics.py       Windows 화면 지표 — 폰트 경로, 트레이 아이콘 크기, DPI 배율, 가상 화면
  icon_render.py      HudState → 트레이 아이콘 이미지 (순수 함수)
  overlay.py          tkinter 창
  tray.py             pystray 아이콘과 메뉴
  autostart.py        시작 프로그램 등록/해제
tests/
  test_models.py        test_http_client.py   test_config.py
  test_theme.py         test_formatting.py    test_credentials.py
  test_usage_client.py  test_poller.py        test_winmetrics.py
  test_icon_render.py   test_autostart.py
pyproject.toml
```

`http_client.py`를 따로 둔 이유는 나머지 전부를 네트워크 없이 테스트하기 위해서다. `credentials`와 `usage_client`는 요청 함수를 주입받는다.

`theme.py`·`formatting.py`·`icon_render.py`는 순수 함수만 담는다. UI에서 가장 틀리기 쉬운 부분을 UI 없이 검증하기 위한 분리다.

`winmetrics.py`는 **PC마다 다른 값을 한 곳에 가둔다.** 윈도우 설치 드라이브, 화면 배율, 모니터 구성이 여기서만 다뤄지고 나머지 모듈은 그 차이를 모른다. ctypes 호출은 얇게 두고 판정 로직만 순수 함수로 빼 테스트한다.

---

### Task 1: 프로젝트 스캐폴딩과 도메인 타입

**Files:**
- Create: `pyproject.toml`
- Create: `claude_usage_overlay/__init__.py`
- Create: `claude_usage_overlay/models.py`
- Create: `.gitignore`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: 없음 (첫 작업)
- Produces: `Status` (Enum), `UsageSnapshot`, `HudState`, 예외 `ReloginRequired`, `RateLimited`, `Unauthorized`, `SchemaChanged`

- [ ] **Step 1: git 저장소 초기화**

프로젝트 폴더는 아직 git 저장소가 아니다.

```bash
cd /c/Users/r46t8/IdeaProjects/CLAUDE_HUD
git init
```

- [ ] **Step 2: `.gitignore` 작성**

```
__pycache__/
*.py[cod]
.pytest_cache/
.venv/
venv/
.superpowers/
```

- [ ] **Step 3: `pyproject.toml` 작성**

```toml
[project]
name = "claude-usage-overlay"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["pystray>=0.19", "pillow>=10.0"]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 4: 실패하는 테스트 작성**

`tests/test_models.py`:

```python
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


def test_hud_state_can_carry_no_snapshot():
    state = HudState(status=Status.RELOGIN, snapshot=None, detail="재로그인 필요")
    assert state.snapshot is None
    assert state.status is Status.RELOGIN


def test_rate_limited_carries_retry_after():
    err = RateLimited(retry_after=287)
    assert err.retry_after == 287
```

- [ ] **Step 5: 테스트 실패 확인**

Run: `python -m pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claude_usage_overlay'`

- [ ] **Step 6: `claude_usage_overlay/__init__.py` 작성 (빈 파일)**

```python
```

- [ ] **Step 7: `claude_usage_overlay/models.py` 작성**

```python
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
    resets_at: datetime
    seven_day_pct: float | None
    fetched_at: datetime


@dataclass(frozen=True)
class HudState:
    """폴러가 만들고 UI가 소비하는 값. UI는 이것만 보면 된다."""

    status: Status
    snapshot: UsageSnapshot | None
    detail: str


class ReloginRequired(Exception):
    """refreshToken까지 만료되어 사용자가 claude auth login을 해야 하는 상태."""


class RateLimited(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__(f"rate limited, retry after {retry_after}s")
        self.retry_after = retry_after


class Unauthorized(Exception):
    """401. 토큰을 갱신하면 회복될 수 있다."""


class SchemaChanged(Exception):
    """응답 형식이 예상과 다르다. 숫자를 지어내지 않고 이 예외를 던진다."""
```

- [ ] **Step 8: 테스트 통과 확인**

Run: `python -m pytest tests/test_models.py -v`
Expected: PASS (4 passed)

- [ ] **Step 9: 커밋**

```bash
git add pyproject.toml .gitignore claude_usage_overlay/ tests/
git commit -m "feat: 프로젝트 스캐폴딩과 도메인 타입 추가"
```

---

### Task 2: HTTP 어댑터

**Files:**
- Create: `claude_usage_overlay/http_client.py`
- Test: `tests/test_http_client.py`

**Interfaces:**
- Consumes: 없음
- Produces: `HttpResponse(status: int, body: bytes, headers: dict[str, str])`,
  `request(method: str, url: str, headers: dict[str, str], json_body: dict | None = None, timeout: float = 10.0) -> HttpResponse`

이 어댑터는 **4xx/5xx에서도 예외를 던지지 않고 응답을 그대로 반환한다.** 429의 `retry-after` 헤더를 읽어야 하기 때문이다. 헤더 키는 소문자로 정규화한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_http_client.py`:

```python
import io
import urllib.error

from claude_usage_overlay.http_client import HttpResponse, request


class FakeHTTPError(urllib.error.HTTPError):
    def __init__(self, status, body, headers):
        super().__init__("http://x", status, "err", headers, io.BytesIO(body))


def test_returns_body_and_normalized_headers(monkeypatch):
    class FakeResponse:
        status = 200
        headers = {"Retry-After": "12", "Content-Type": "application/json"}

        def read(self):
            return b'{"ok": true}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        "claude_usage_overlay.http_client.urlopen",
        lambda req, timeout: FakeResponse(),
    )

    res = request("GET", "http://x", {"Authorization": "Bearer t"})
    assert isinstance(res, HttpResponse)
    assert res.status == 200
    assert res.body == b'{"ok": true}'
    assert res.headers["retry-after"] == "12"


def test_http_error_is_returned_not_raised(monkeypatch):
    def boom(req, timeout):
        raise FakeHTTPError(429, b'{"error": "rate"}', {"Retry-After": "287"})

    monkeypatch.setattr("claude_usage_overlay.http_client.urlopen", boom)

    res = request("GET", "http://x", {})
    assert res.status == 429
    assert res.headers["retry-after"] == "287"
    assert b"rate" in res.body
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_http_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claude_usage_overlay.http_client'`

- [ ] **Step 3: `claude_usage_overlay/http_client.py` 작성**

```python
"""urllib 어댑터. 다른 모듈은 urllib를 직접 쓰지 않는다."""

import json
import urllib.error
from dataclasses import dataclass
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes
    headers: dict[str, str]


def _normalize(headers) -> dict[str, str]:
    return {str(k).lower(): str(v) for k, v in dict(headers).items()}


def request(
    method: str,
    url: str,
    headers: dict[str, str],
    json_body: dict | None = None,
    timeout: float = 10.0,
) -> HttpResponse:
    """4xx/5xx에서도 예외를 던지지 않는다. 429의 retry-after를 읽어야 하기 때문."""
    data = None
    send_headers = dict(headers)
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        send_headers.setdefault("Content-Type", "application/json")

    req = Request(url, data=data, headers=send_headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as res:
            return HttpResponse(
                status=res.status, body=res.read(), headers=_normalize(res.headers)
            )
    except urllib.error.HTTPError as err:
        return HttpResponse(
            status=err.code, body=err.read(), headers=_normalize(err.headers)
        )
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_http_client.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 커밋**

```bash
git add claude_usage_overlay/http_client.py tests/test_http_client.py
git commit -m "feat: urllib 기반 HTTP 어댑터 추가"
```

---

### Task 3: 설정 파일

**Files:**
- Create: `claude_usage_overlay/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: 없음
- Produces: `Config` 데이터클래스(필드 `x`, `y`, `poll_seconds`, `warn_pct`, `danger_pct`, `overlay_visible`),
  `config_path() -> Path`, `load_config(path: Path | None = None) -> Config`, `save_config(cfg: Config, path: Path | None = None) -> None`

설정 파일이 없거나 깨져 있으면 **예외를 던지지 않고 기본값을 쓴다.** 설정 하나 때문에 HUD 전체가 안 뜨면 안 된다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_config.py`:

```python
import json

from claude_usage_overlay.config import Config, load_config, save_config


def test_missing_file_returns_defaults(tmp_path):
    cfg = load_config(tmp_path / "none.json")
    assert cfg.poll_seconds == 300
    assert cfg.warn_pct == 70
    assert cfg.danger_pct == 90
    assert cfg.overlay_visible is True
    assert cfg.x is None and cfg.y is None


def test_broken_json_returns_defaults(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{ this is not json", encoding="utf-8")
    assert load_config(p).poll_seconds == 300


def test_partial_file_fills_missing_with_defaults(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"x": 100, "y": 200}), encoding="utf-8")
    cfg = load_config(p)
    assert cfg.x == 100
    assert cfg.y == 200
    assert cfg.warn_pct == 70


def test_save_then_load_roundtrip(tmp_path):
    p = tmp_path / "nested" / "config.json"
    save_config(Config(x=12, y=34, poll_seconds=600), p)
    cfg = load_config(p)
    assert (cfg.x, cfg.y, cfg.poll_seconds) == (12, 34, 600)


def test_poll_seconds_floor_is_enforced(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"poll_seconds": 5}), encoding="utf-8")
    # 엔드포인트에 호출 한도가 있으므로 너무 짧은 값은 60초로 올린다
    assert load_config(p).poll_seconds == 60
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claude_usage_overlay.config'`

- [ ] **Step 3: `claude_usage_overlay/config.py` 작성**

```python
"""설정 파일. 깨져 있어도 기본값으로 계속 동작한다."""

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

MIN_POLL_SECONDS = 60


@dataclass
class Config:
    x: int | None = None
    y: int | None = None
    poll_seconds: int = 300
    warn_pct: int = 70
    danger_pct: int = 90
    overlay_visible: bool = True


def config_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "claude-usage-overlay" / "config.json"


def load_config(path: Path | None = None) -> Config:
    path = path or config_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raw = {}
    except (OSError, json.JSONDecodeError):
        raw = {}

    known = {f for f in Config.__dataclass_fields__}
    cfg = Config(**{k: v for k, v in raw.items() if k in known})
    cfg.poll_seconds = max(MIN_POLL_SECONDS, int(cfg.poll_seconds))
    return cfg


def save_config(cfg: Config, path: Path | None = None) -> None:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")
    os.replace(tmp, path)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: 커밋**

```bash
git add claude_usage_overlay/config.py tests/test_config.py
git commit -m "feat: 설정 로드/저장 추가"
```

---

### Task 4: 색과 문구 (순수 함수)

**Files:**
- Create: `claude_usage_overlay/theme.py`
- Create: `claude_usage_overlay/formatting.py`
- Test: `tests/test_theme.py`
- Test: `tests/test_formatting.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `theme.GREEN`, `theme.YELLOW`, `theme.RED`, `theme.GREY`, `theme.BG`, `theme.TEXT_LIGHT`, `theme.TEXT_DARK` (모두 `str`, `#rrggbb`)
  - `theme.color_for(pct: float, warn: int = 70, danger: int = 90) -> str`
  - `formatting.format_countdown(resets_at: datetime, now: datetime) -> str`
  - `formatting.format_age(fetched_at: datetime, now: datetime) -> str`
  - `formatting.format_stale_detail(fetched_at: datetime, now: datetime) -> str`

- [ ] **Step 1: 실패하는 테스트 작성 (theme)**

`tests/test_theme.py`:

```python
from claude_usage_overlay import theme


def test_below_warn_is_green():
    assert theme.color_for(0) == theme.GREEN
    assert theme.color_for(69.9) == theme.GREEN


def test_warn_band_is_yellow():
    assert theme.color_for(70) == theme.YELLOW
    assert theme.color_for(89.9) == theme.YELLOW


def test_danger_band_is_red():
    assert theme.color_for(90) == theme.RED
    assert theme.color_for(100) == theme.RED


def test_custom_thresholds_are_honored():
    assert theme.color_for(55, warn=50, danger=80) == theme.YELLOW
    assert theme.color_for(85, warn=50, danger=80) == theme.RED
```

- [ ] **Step 2: 실패하는 테스트 작성 (formatting)**

`tests/test_formatting.py`:

```python
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


def test_age_under_a_minute_says_just_now():
    assert format_age(NOW - timedelta(seconds=30), NOW) == "방금 갱신됨"


def test_age_in_minutes():
    assert format_age(NOW - timedelta(minutes=14), NOW) == "14분 전 갱신"


def test_age_in_hours():
    assert format_age(NOW - timedelta(hours=3), NOW) == "3시간 전 갱신"


def test_stale_detail_counts_minutes_since_last_success():
    assert format_stale_detail(NOW - timedelta(minutes=14), NOW) == "14분째 갱신 실패"
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `python -m pytest tests/test_theme.py tests/test_formatting.py -v`
Expected: FAIL — 두 모듈 모두 `ModuleNotFoundError`

- [ ] **Step 4: `claude_usage_overlay/theme.py` 작성**

```python
"""사용률 → 색. 오버레이와 트레이 아이콘이 같은 함수를 쓴다."""

GREEN = "#63e6be"
YELLOW = "#f6c177"
RED = "#ff8f8f"
GREY = "#4a4a52"
BG = "#262b36"
TEXT_LIGHT = "#e8ecf2"
TEXT_DARK = "#0f1115"


def color_for(pct: float, warn: int = 70, danger: int = 90) -> str:
    if pct >= danger:
        return RED
    if pct >= warn:
        return YELLOW
    return GREEN
```

- [ ] **Step 5: `claude_usage_overlay/formatting.py` 작성**

```python
"""시각 → 한국어 문구. 오버레이는 이 함수들만 호출한다."""

from datetime import datetime


def format_countdown(resets_at: datetime, now: datetime) -> str:
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
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `python -m pytest tests/test_theme.py tests/test_formatting.py -v`
Expected: PASS (11 passed)

- [ ] **Step 7: 커밋**

```bash
git add claude_usage_overlay/theme.py claude_usage_overlay/formatting.py tests/test_theme.py tests/test_formatting.py
git commit -m "feat: 색 임계값과 한국어 문구 포맷터 추가"
```

---

### Task 5: 자격증명 수명 관리

**Files:**
- Create: `claude_usage_overlay/credentials.py`
- Test: `tests/test_credentials.py`

**Interfaces:**
- Consumes: `models.ReloginRequired`, `http_client.request`, `http_client.HttpResponse`
- Produces: `CredentialStore(path: Path | None = None, request_fn=http_client.request, now_ms=<현재시각 ms 반환 콜러블>)`,
  메서드 `get_access_token() -> str`, `force_refresh() -> str`
  상수 `CREDENTIALS_PATH`, `TOKEN_URL`, `CLIENT_ID`, `REFRESH_MARGIN_MS`

**이 프로젝트에서 가장 위험한 모듈이다.** 갱신 응답의 `refresh_token`은 매번 회전한다. 새 값을 저장하지 못하면 이전 값은 이미 죽어 있어 사용자가 `claude auth login`을 다시 해야 한다. 방어 세 가지를 모두 구현한다.

1. 원자적 쓰기 (`os.replace`)
2. 갱신 직전 파일 재읽기 — Claude Code CLI가 먼저 갱신했을 수 있다
3. 만료 30분 전에만 갱신 — 회전 횟수를 줄인다

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_credentials.py`:

```python
import json

import pytest

from claude_usage_overlay.credentials import CredentialStore
from claude_usage_overlay.http_client import HttpResponse
from claude_usage_overlay.models import ReloginRequired

NOW_MS = 1_786_331_000_000
HOUR_MS = 3_600_000


def write_creds(path, *, access="acc-old", refresh="ref-old", expires_at=None, refresh_expires_at=None):
    path.write_text(
        json.dumps(
            {
                "claudeAiOauth": {
                    "accessToken": access,
                    "refreshToken": refresh,
                    "expiresAt": expires_at if expires_at is not None else NOW_MS + 8 * HOUR_MS,
                    "refreshTokenExpiresAt": refresh_expires_at
                    if refresh_expires_at is not None
                    else NOW_MS + 30 * 24 * HOUR_MS,
                    "scopes": ["user:profile"],
                    "subscriptionType": "max",
                }
            }
        ),
        encoding="utf-8",
    )


def ok_refresh_response(**over):
    payload = {
        "access_token": "acc-new",
        "refresh_token": "ref-new",
        "expires_in": 28800,
        "refresh_token_expires_in": 2585692,
    }
    payload.update(over)
    return HttpResponse(200, json.dumps(payload).encode(), {})


def test_valid_token_is_returned_without_network(tmp_path):
    p = tmp_path / ".credentials.json"
    write_creds(p)

    def no_network(*a, **k):
        raise AssertionError("갱신이 필요 없는데 네트워크를 호출했다")

    store = CredentialStore(path=p, request_fn=no_network, now_ms=lambda: NOW_MS)
    assert store.get_access_token() == "acc-old"


def test_token_near_expiry_is_refreshed_and_written_back(tmp_path):
    p = tmp_path / ".credentials.json"
    write_creds(p, expires_at=NOW_MS + 10 * 60 * 1000)  # 10분 뒤 만료 → 30분 마진 안

    calls = []

    def fake_request(method, url, headers, json_body=None, timeout=10.0):
        calls.append((method, url, json_body))
        return ok_refresh_response()

    store = CredentialStore(path=p, request_fn=fake_request, now_ms=lambda: NOW_MS)
    assert store.get_access_token() == "acc-new"

    assert calls[0][0] == "POST"
    assert calls[0][2]["grant_type"] == "refresh_token"
    assert calls[0][2]["refresh_token"] == "ref-old"

    saved = json.loads(p.read_text(encoding="utf-8"))["claudeAiOauth"]
    assert saved["accessToken"] == "acc-new"
    assert saved["refreshToken"] == "ref-new"          # 회전된 값이 저장돼야 한다
    assert saved["expiresAt"] == NOW_MS + 28800 * 1000
    assert saved["refreshTokenExpiresAt"] == NOW_MS + 2585692 * 1000
    assert saved["subscriptionType"] == "max"          # 모르는 필드는 보존


def test_external_refresh_is_detected_and_reused(tmp_path):
    """갱신 직전 파일을 다시 읽어, CLI가 이미 갱신했으면 우리는 갱신하지 않는다."""
    p = tmp_path / ".credentials.json"
    write_creds(p, expires_at=NOW_MS + 10 * 60 * 1000)

    def fake_request(method, url, headers, json_body=None, timeout=10.0):
        raise AssertionError("외부에서 이미 갱신됐는데 또 갱신했다")

    store = CredentialStore(path=p, request_fn=fake_request, now_ms=lambda: NOW_MS)
    # 다른 프로세스가 파일을 갱신한 상황을 흉내낸다
    write_creds(p, access="acc-from-cli", expires_at=NOW_MS + 8 * HOUR_MS)

    assert store.get_access_token() == "acc-from-cli"


def test_refresh_failure_raises_relogin_required(tmp_path):
    p = tmp_path / ".credentials.json"
    write_creds(p, expires_at=NOW_MS - 1000)

    def fake_request(*a, **k):
        return HttpResponse(400, b'{"error":"invalid_grant"}', {})

    store = CredentialStore(path=p, request_fn=fake_request, now_ms=lambda: NOW_MS)
    with pytest.raises(ReloginRequired):
        store.get_access_token()


def test_failed_refresh_leaves_file_untouched(tmp_path):
    p = tmp_path / ".credentials.json"
    write_creds(p, expires_at=NOW_MS - 1000)
    before = p.read_text(encoding="utf-8")

    store = CredentialStore(
        path=p,
        request_fn=lambda *a, **k: HttpResponse(400, b"{}", {}),
        now_ms=lambda: NOW_MS,
    )
    with pytest.raises(ReloginRequired):
        store.get_access_token()

    assert p.read_text(encoding="utf-8") == before


def test_missing_file_raises_relogin_required(tmp_path):
    store = CredentialStore(
        path=tmp_path / "nope.json", request_fn=lambda *a, **k: None, now_ms=lambda: NOW_MS
    )
    with pytest.raises(ReloginRequired):
        store.get_access_token()


def test_force_refresh_rereads_file_before_refreshing(tmp_path):
    """401을 받았을 때: 우리 토큰을 버리기 전에 파일부터 다시 읽는다."""
    p = tmp_path / ".credentials.json"
    write_creds(p, access="acc-old", expires_at=NOW_MS + 8 * HOUR_MS)

    store = CredentialStore(
        path=p, request_fn=lambda *a, **k: ok_refresh_response(), now_ms=lambda: NOW_MS
    )
    store.get_access_token()  # acc-old 캐시

    write_creds(p, access="acc-from-cli", expires_at=NOW_MS + 8 * HOUR_MS)
    assert store.force_refresh() == "acc-from-cli"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_credentials.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claude_usage_overlay.credentials'`

- [ ] **Step 3: `claude_usage_overlay/credentials.py` 작성**

```python
"""토큰 수명 관리.

refreshToken은 갱신할 때마다 회전한다. 새 값을 저장하지 못하면 이전 값은
이미 죽어 있어 사용자가 claude auth login을 다시 해야 한다. 이 파일의
모든 복잡성은 그 사고를 막기 위한 것이다.
"""

import json
import os
import time
from pathlib import Path
from typing import Callable

from . import http_client
from .models import ReloginRequired

CREDENTIALS_PATH = Path(os.environ.get("USERPROFILE", str(Path.home()))) / ".claude" / ".credentials.json"
TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
REFRESH_MARGIN_MS = 30 * 60 * 1000

OAUTH_KEY = "claudeAiOauth"


def _now_ms() -> int:
    return int(time.time() * 1000)


class CredentialStore:
    def __init__(
        self,
        path: Path | None = None,
        request_fn: Callable = http_client.request,
        now_ms: Callable[[], int] = _now_ms,
    ) -> None:
        self._path = path or CREDENTIALS_PATH
        self._request = request_fn
        self._now_ms = now_ms

    # --- 공개 인터페이스 -------------------------------------------------

    def get_access_token(self) -> str:
        """유효한 accessToken을 돌려준다. 필요하면 갱신하고 저장한다."""
        creds = self._read()
        if not self._needs_refresh(creds):
            return creds["accessToken"]
        return self._refresh_and_store(creds)

    def force_refresh(self) -> str:
        """401을 받았을 때 호출한다. 파일을 먼저 다시 읽는다 —
        다른 프로세스가 이미 갱신해 뒀을 수 있기 때문이다."""
        creds = self._read()
        if not self._needs_refresh(creds):
            return creds["accessToken"]
        return self._refresh_and_store(creds)

    # --- 내부 ------------------------------------------------------------

    def _read(self) -> dict:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            creds = raw[OAUTH_KEY]
            if not creds.get("accessToken") or not creds.get("refreshToken"):
                raise KeyError("token missing")
            return creds
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as err:
            raise ReloginRequired(f"자격증명을 읽을 수 없습니다: {err}") from err

    def _needs_refresh(self, creds: dict) -> bool:
        expires_at = int(creds.get("expiresAt") or 0)
        return expires_at - self._now_ms() <= REFRESH_MARGIN_MS

    def _refresh_and_store(self, creds: dict) -> str:
        # 방어 2: 갱신 직전에 파일을 다시 읽는다. CLI가 먼저 갱신했을 수 있다.
        fresh = self._read()
        if not self._needs_refresh(fresh):
            return fresh["accessToken"]

        res = self._request(
            "POST",
            TOKEN_URL,
            {"Content-Type": "application/json"},
            json_body={
                "grant_type": "refresh_token",
                "refresh_token": fresh["refreshToken"],
                "client_id": CLIENT_ID,
            },
        )
        if res is None or res.status != 200:
            status = getattr(res, "status", "no response")
            raise ReloginRequired(
                f"토큰 갱신 실패({status}). 터미널에서 claude auth login 을 실행하세요."
            )

        try:
            data = json.loads(res.body)
            access = data["access_token"]
        except (json.JSONDecodeError, KeyError, TypeError) as err:
            raise ReloginRequired(f"갱신 응답 형식이 예상과 다릅니다: {err}") from err

        now = self._now_ms()
        updated = dict(fresh)  # 모르는 필드도 그대로 보존한다
        updated["accessToken"] = access
        updated["refreshToken"] = data.get("refresh_token", fresh["refreshToken"])
        if data.get("expires_in"):
            updated["expiresAt"] = now + int(data["expires_in"]) * 1000
        if data.get("refresh_token_expires_in"):
            updated["refreshTokenExpiresAt"] = now + int(data["refresh_token_expires_in"]) * 1000

        self._write_atomic(updated)
        return access

    def _write_atomic(self, creds: dict) -> None:
        """방어 1: 임시 파일에 쓰고 os.replace. 쓰다 죽어도 파일이 반쯤 망가지지 않는다."""
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        raw[OAUTH_KEY] = creds

        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_credentials.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: 커밋**

```bash
git add claude_usage_overlay/credentials.py tests/test_credentials.py
git commit -m "feat: 토큰 회전에 안전한 자격증명 저장소 추가"
```

---

### Task 6: 사용량 클라이언트

**Files:**
- Create: `claude_usage_overlay/usage_client.py`
- Test: `tests/test_usage_client.py`

**Interfaces:**
- Consumes: `models.UsageSnapshot`, `models.RateLimited`, `models.Unauthorized`, `models.SchemaChanged`, `http_client.request`
- Produces: `fetch_usage(token: str, request_fn=http_client.request, now=<현재 UTC datetime 반환 콜러블>) -> UsageSnapshot`,
  상수 `USAGE_URL`, `BETA_HEADER`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_usage_client.py`:

```python
import json
from datetime import datetime, timezone

import pytest

from claude_usage_overlay.http_client import HttpResponse
from claude_usage_overlay.models import RateLimited, SchemaChanged, Unauthorized
from claude_usage_overlay.usage_client import fetch_usage

NOW = datetime(2026, 8, 10, 3, 25, tzinfo=timezone.utc)

BODY = {
    "five_hour": {"utilization": 23, "resets_at": "2026-08-10T05:40:00.296352+00:00"},
    "seven_day": {"utilization": 15, "resets_at": "2026-08-12T17:00:00.296375+00:00"},
    "seven_day_opus": None,
}


def responder(status, body, headers=None):
    payload = body if isinstance(body, bytes) else json.dumps(body).encode()
    return lambda *a, **k: HttpResponse(status, payload, headers or {})


def test_parses_five_hour_and_seven_day():
    snap = fetch_usage("tok", request_fn=responder(200, BODY), now=lambda: NOW)
    assert snap.five_hour_pct == 23
    assert snap.seven_day_pct == 15
    assert snap.resets_at == datetime(2026, 8, 10, 5, 40, 0, 296352, tzinfo=timezone.utc)
    assert snap.fetched_at == NOW


def test_sends_required_headers():
    seen = {}

    def spy(method, url, headers, json_body=None, timeout=10.0):
        seen.update(headers)
        seen["_url"] = url
        return HttpResponse(200, json.dumps(BODY).encode(), {})

    fetch_usage("tok-123", request_fn=spy, now=lambda: NOW)
    assert seen["Authorization"] == "Bearer tok-123"
    assert seen["anthropic-beta"] == "oauth-2025-04-20"
    assert seen["_url"] == "https://api.anthropic.com/api/oauth/usage"


def test_missing_seven_day_is_none():
    body = {"five_hour": BODY["five_hour"], "seven_day": None}
    snap = fetch_usage("tok", request_fn=responder(200, body), now=lambda: NOW)
    assert snap.seven_day_pct is None


def test_429_raises_rate_limited_with_retry_after():
    fn = responder(429, {"error": "rate"}, {"retry-after": "287"})
    with pytest.raises(RateLimited) as exc:
        fetch_usage("tok", request_fn=fn, now=lambda: NOW)
    assert exc.value.retry_after == 287


def test_429_without_header_falls_back_to_300():
    with pytest.raises(RateLimited) as exc:
        fetch_usage("tok", request_fn=responder(429, {}), now=lambda: NOW)
    assert exc.value.retry_after == 300


def test_401_raises_unauthorized():
    with pytest.raises(Unauthorized):
        fetch_usage("tok", request_fn=responder(401, {"error": "auth"}), now=lambda: NOW)


def test_missing_five_hour_raises_schema_changed():
    with pytest.raises(SchemaChanged):
        fetch_usage("tok", request_fn=responder(200, {"seven_day": None}), now=lambda: NOW)


def test_invalid_json_raises_schema_changed():
    with pytest.raises(SchemaChanged):
        fetch_usage("tok", request_fn=responder(200, b"not json"), now=lambda: NOW)


def test_unexpected_status_raises_schema_changed():
    with pytest.raises(SchemaChanged):
        fetch_usage("tok", request_fn=responder(500, {}), now=lambda: NOW)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_usage_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claude_usage_overlay.usage_client'`

- [ ] **Step 3: `claude_usage_overlay/usage_client.py` 작성**

```python
"""사용량 엔드포인트 → UsageSnapshot. HTTP와 도메인의 경계."""

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
        five_hour = data["five_hour"]
        pct = float(five_hour["utilization"])
        resets_at = datetime.fromisoformat(five_hour["resets_at"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as err:
        raise SchemaChanged(f"응답 형식이 예상과 다릅니다: {err}") from err

    return UsageSnapshot(
        five_hour_pct=pct,
        resets_at=resets_at,
        seven_day_pct=_window_pct(data.get("seven_day")),
        fetched_at=now(),
    )
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_usage_client.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: 커밋**

```bash
git add claude_usage_overlay/usage_client.py tests/test_usage_client.py
git commit -m "feat: 사용량 엔드포인트 클라이언트 추가"
```

---

### Task 7: 폴러

**Files:**
- Create: `claude_usage_overlay/poller.py`
- Test: `tests/test_poller.py`

**Interfaces:**
- Consumes: `credentials.CredentialStore`, `usage_client.fetch_usage`, `config.Config`, `models.*`, `formatting.format_stale_detail`
- Produces: `Poller(store, config, fetch_fn=fetch_usage, now=<UTC datetime 콜러블>)`,
  메서드 `step() -> int` (다음 호출까지 대기할 초), `state() -> HudState`, `start() -> None`, `stop() -> None`, `request_now() -> None`
  상수 `MAX_BACKOFF_SECONDS = 1800`

`step()`이 로직 전부다. 스레드 없이 이것만 테스트한다. `start()`는 `step()`을 반복 호출하는 얇은 껍데기다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_poller.py`:

```python
from datetime import datetime, timedelta, timezone

from claude_usage_overlay.config import Config
from claude_usage_overlay.models import (
    RateLimited,
    ReloginRequired,
    SchemaChanged,
    Status,
    Unauthorized,
    UsageSnapshot,
)
from claude_usage_overlay.poller import Poller

NOW = datetime(2026, 8, 10, 3, 25, tzinfo=timezone.utc)


class FakeStore:
    def __init__(self, token="tok", force_error=None):
        self.token = token
        self.force_calls = 0
        self.force_error = force_error

    def get_access_token(self):
        return self.token

    def force_refresh(self):
        self.force_calls += 1
        if self.force_error:
            raise self.force_error
        return self.token


def snapshot(at=NOW, pct=23.0):
    return UsageSnapshot(
        five_hour_pct=pct,
        resets_at=at + timedelta(hours=2),
        seven_day_pct=15.0,
        fetched_at=at,
    )


def make(fetch_fn, store=None, now=NOW):
    clock = {"t": now}
    p = Poller(
        store=store or FakeStore(),
        config=Config(poll_seconds=300),
        fetch_fn=fetch_fn,
        now=lambda: clock["t"],
    )
    return p, clock


def test_success_produces_ok_state_and_base_delay():
    p, _ = make(lambda token, **k: snapshot())
    delay = p.step()
    assert delay == 300
    assert p.state().status is Status.OK
    assert p.state().snapshot.five_hour_pct == 23.0


def test_failure_after_success_is_stale_and_keeps_last_snapshot():
    calls = {"n": 0}

    def flaky(token, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return snapshot()
        raise OSError("network down")

    p, clock = make(flaky)
    p.step()
    clock["t"] = NOW + timedelta(minutes=14)
    delay = p.step()

    state = p.state()
    assert state.status is Status.STALE
    assert state.snapshot.five_hour_pct == 23.0   # 마지막 값을 유지한다
    assert state.detail == "14분째 갱신 실패"
    assert delay == 300                            # 첫 실패는 기본 주기


def test_backoff_doubles_and_caps():
    p, _ = make(lambda token, **k: (_ for _ in ()).throw(OSError("down")))
    assert p.step() == 300     # 1회 실패
    assert p.step() == 600     # 2회
    assert p.step() == 1200    # 3회
    assert p.step() == 1800    # 4회 — 상한
    assert p.step() == 1800    # 5회 — 상한 유지


def test_success_resets_backoff():
    calls = {"n": 0}

    def flaky(token, **k):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise OSError("down")
        return snapshot()

    p, _ = make(flaky)
    p.step()
    p.step()
    assert p.step() == 300


def test_rate_limited_honors_retry_after():
    p, _ = make(lambda token, **k: (_ for _ in ()).throw(RateLimited(287)))
    delay = p.step()
    assert delay == 292                      # retry_after + 5초 여유
    assert p.state().status is Status.RATE_LIMITED


def test_unauthorized_triggers_force_refresh_then_retries_next_tick():
    store = FakeStore()
    p, _ = make(lambda token, **k: (_ for _ in ()).throw(Unauthorized()), store=store)
    p.step()
    assert store.force_calls == 1


def test_relogin_required_is_terminal_state():
    store = FakeStore(force_error=ReloginRequired("dead"))
    p, _ = make(lambda token, **k: (_ for _ in ()).throw(Unauthorized()), store=store)
    p.step()
    state = p.state()
    assert state.status is Status.RELOGIN
    assert "claude auth login" in state.detail


def test_schema_change_is_reported_not_guessed():
    p, _ = make(lambda token, **k: (_ for _ in ()).throw(SchemaChanged("no five_hour")))
    p.step()
    assert p.state().status is Status.SCHEMA_ERROR
    assert p.state().snapshot is None


def test_initial_state_before_first_step():
    p, _ = make(lambda token, **k: snapshot())
    assert p.state().status is Status.STALE
    assert p.state().snapshot is None
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_poller.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claude_usage_overlay.poller'`

- [ ] **Step 3: `claude_usage_overlay/poller.py` 작성**

```python
"""주기 조회, 백오프, 상태 판정.

로직은 전부 step() 안에 있다. start()는 step()을 반복하는 껍데기라
스레드 없이 step()만 테스트하면 된다.
"""

import threading
from datetime import datetime, timezone
from typing import Callable

from .config import Config
from .formatting import format_stale_detail
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
        self._state = HudState(Status.STALE, None, "불러오는 중")
        self._last_snapshot: UsageSnapshot | None = None
        self._failures = 0

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
            self._set(Status.RATE_LIMITED, self._last_snapshot, "호출 한도 — 잠시 후 재시도")
            return err.retry_after + RATE_LIMIT_PADDING
        except Unauthorized:
            return self._handle_unauthorized()
        except ReloginRequired as err:
            self._set(Status.RELOGIN, None, "재로그인 필요 — claude auth login")
            return self._backoff()
        except SchemaChanged:
            self._set(Status.SCHEMA_ERROR, None, "응답 형식이 바뀌었습니다")
            return self._backoff()
        except Exception:  # 네트워크 오류 등
            return self._handle_transient()

        self._failures = 0
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
        """트레이의 '지금 갱신' 메뉴가 호출한다."""
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
        try:
            self._store.force_refresh()
        except ReloginRequired:
            self._set(Status.RELOGIN, None, "재로그인 필요 — claude auth login")
            return self._backoff()
        # 갱신에 성공했으면 다음 틱에서 다시 조회한다
        self._mark_stale()
        return self._backoff()

    def _handle_transient(self) -> int:
        self._mark_stale()
        return self._backoff()

    def _mark_stale(self) -> None:
        if self._last_snapshot is None:
            self._set(Status.STALE, None, "아직 데이터가 없습니다")
            return
        detail = format_stale_detail(self._last_snapshot.fetched_at, self._now())
        self._set(Status.STALE, self._last_snapshot, detail)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_poller.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: 전체 테스트 실행**

Run: `python -m pytest -v`
Expected: PASS (모든 테스트 통과)

- [ ] **Step 6: 커밋**

```bash
git add claude_usage_overlay/poller.py tests/test_poller.py
git commit -m "feat: 백오프와 상태 판정을 담당하는 폴러 추가"
```

---

### Task 8: Windows 화면 지표

**Files:**
- Create: `claude_usage_overlay/winmetrics.py`
- Test: `tests/test_winmetrics.py`

**Interfaces:**
- Consumes: 없음
- Produces: `fonts_dir() -> Path`, `system_icon_size() -> int`, `dpi_scale() -> float`,
  `virtual_screen_rect() -> tuple[int, int, int, int]`,
  `is_position_visible(x: int, y: int, w: int, h: int, rect: tuple[int, int, int, int]) -> bool`,
  상수 `MIN_VISIBLE_W = 40`, `MIN_VISIBLE_H = 20`

이 프로그램은 특정 PC가 아니라 임의의 윈도우 환경에서 돌아야 한다. PC마다 달라지는 값 세 가지를 이 모듈에 가둔다.

- 윈도우가 C: 아닌 드라이브에 설치돼 있을 수 있다 → `fonts_dir()`
- 배율이 100%가 아니면 트레이 아이콘은 16px이 아니다 → `system_icon_size()`
- 저장된 창 위치가 지금 없는 모니터를 가리킬 수 있다 → `is_position_visible()`

ctypes로 Windows API를 부르는 부분은 얇게 두고, **판정 로직인 `is_position_visible`만 순수 함수로 빼서 테스트한다.**

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_winmetrics.py`:

```python
from pathlib import Path

from claude_usage_overlay import winmetrics


def test_fonts_dir_follows_windir(monkeypatch):
    monkeypatch.setenv("WINDIR", r"D:\Windows")
    assert winmetrics.fonts_dir() == Path(r"D:\Windows\Fonts")


def test_fonts_dir_falls_back_when_windir_missing(monkeypatch):
    monkeypatch.delenv("WINDIR", raising=False)
    assert winmetrics.fonts_dir() == Path(r"C:\Windows\Fonts")


def test_system_icon_size_is_plausible():
    size = winmetrics.system_icon_size()
    assert isinstance(size, int)
    assert 8 <= size <= 64


def test_dpi_scale_is_at_least_one():
    assert winmetrics.dpi_scale() >= 1.0


def test_virtual_screen_rect_has_positive_extent():
    _x, _y, w, h = winmetrics.virtual_screen_rect()
    assert w > 0 and h > 0


RECT = (0, 0, 2560, 1440)  # x, y, width, height


def test_window_fully_inside_is_visible():
    assert winmetrics.is_position_visible(100, 100, 186, 62, RECT)


def test_window_far_off_to_the_right_is_not_visible():
    assert not winmetrics.is_position_visible(4000, 100, 186, 62, RECT)


def test_window_far_above_is_not_visible():
    assert not winmetrics.is_position_visible(100, -500, 186, 62, RECT)


def test_window_with_enough_overlap_counts_as_visible():
    # 오른쪽 끝에 60px 걸쳐 있으면 드래그로 되찾을 수 있다
    assert winmetrics.is_position_visible(2500, 100, 186, 62, RECT)


def test_window_with_a_sliver_showing_is_not_visible():
    # 20px만 걸쳐 있으면 사실상 못 찾는다
    assert not winmetrics.is_position_visible(2540, 100, 186, 62, RECT)


def test_secondary_monitor_left_of_primary_is_visible():
    # 보조 모니터가 왼쪽에 있으면 가상 화면 원점이 음수다
    rect = (-1920, 0, 4480, 1440)
    assert winmetrics.is_position_visible(-1800, 200, 186, 62, rect)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_winmetrics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claude_usage_overlay.winmetrics'`

- [ ] **Step 3: `claude_usage_overlay/winmetrics.py` 작성**

```python
"""PC마다 달라지는 화면 지표를 한 곳에 가둔다.

윈도우 설치 드라이브, 화면 배율, 모니터 구성은 여기서만 다룬다.
나머지 모듈은 그 차이를 모른다.
"""

import ctypes
import os
from pathlib import Path

SM_CXSMICON = 49
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

DEFAULT_ICON_SIZE = 16
MIN_VISIBLE_W = 40
MIN_VISIBLE_H = 20


def fonts_dir() -> Path:
    """윈도우가 C: 아닌 드라이브에 설치돼 있어도 폰트를 찾는다."""
    return Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"


def _metric(index: int) -> int:
    try:
        return int(ctypes.windll.user32.GetSystemMetrics(index))
    except (AttributeError, OSError):
        return 0


def system_icon_size() -> int:
    """배율 100%에서 16, 125%에서 20, 150%에서 24를 돌려준다."""
    size = _metric(SM_CXSMICON)
    return size if size > 0 else DEFAULT_ICON_SIZE


def dpi_scale() -> float:
    try:
        dpi = int(ctypes.windll.user32.GetDpiForSystem())
    except (AttributeError, OSError):
        dpi = 96
    return max(1.0, dpi / 96.0)


def virtual_screen_rect() -> tuple[int, int, int, int]:
    """모든 모니터를 감싸는 사각형 (x, y, width, height)."""
    width = _metric(SM_CXVIRTUALSCREEN)
    height = _metric(SM_CYVIRTUALSCREEN)
    if width <= 0 or height <= 0:
        return (0, 0, 1920, 1080)
    return (_metric(SM_XVIRTUALSCREEN), _metric(SM_YVIRTUALSCREEN), width, height)


def is_position_visible(
    x: int, y: int, w: int, h: int, rect: tuple[int, int, int, int]
) -> bool:
    """창이 화면에 충분히 걸쳐 있어 사용자가 드래그로 되찾을 수 있는지.

    모니터를 뽑으면 저장된 좌표가 아무 화면에도 없는 영역을 가리킬 수 있다.
    그때 창이 보이지 않는 곳에 떠서 되찾을 방법이 없어지는 것을 막는다.
    """
    rx, ry, rw, rh = rect
    overlap_w = min(x + w, rx + rw) - max(x, rx)
    overlap_h = min(y + h, ry + rh) - max(y, ry)
    return overlap_w >= MIN_VISIBLE_W and overlap_h >= MIN_VISIBLE_H
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_winmetrics.py -v`
Expected: PASS (11 passed)

- [ ] **Step 5: 이 PC의 실측값 확인**

Run:

```bash
python -c "from claude_usage_overlay import winmetrics as w; print('fonts:', w.fonts_dir()); print('icon:', w.system_icon_size()); print('scale:', w.dpi_scale()); print('screen:', w.virtual_screen_rect())"
```

Expected: `fonts` 아래에 `segoeuib.ttf`가 실제로 존재하고, `icon`이 8~64 사이, `scale`이 1.0 이상, `screen`의 폭이 모든 모니터를 합친 값. 개발 PC 기준 예상값은 icon=16, scale=1.0이지만 **다른 값이 나와도 정상이다** — 배율이 다른 PC라는 뜻이다.

- [ ] **Step 6: 커밋**

```bash
git add claude_usage_overlay/winmetrics.py tests/test_winmetrics.py
git commit -m "feat: PC별 화면 지표를 흡수하는 winmetrics 추가"
```

---

### Task 9: 트레이 아이콘 렌더링

**Files:**
- Create: `claude_usage_overlay/icon_render.py`
- Test: `tests/test_icon_render.py`

**Interfaces:**
- Consumes: `models.HudState`, `models.Status`, `theme.*`, `winmetrics.fonts_dir`, `winmetrics.system_icon_size`
- Produces: `render_icon(state: HudState, size: int | None = None, warn: int = 70, danger: int = 90) -> PIL.Image.Image`
  — `size`가 `None`이면 `winmetrics.system_icon_size()`를 쓴다. 테스트는 항상 크기를 명시한다.

**디자인 확정 사항 (스펙 7장):**
- 배경은 어두운 라운드 사각형(`theme.BG`), 사용률만큼 **아래에서 위로** 색이 차오른다
- 숫자를 두 번 그린다 — 채운 영역 위에서는 어두운 글자, 빈 영역 위에서는 밝은 글자. 수위선에서 색이 갈린다
- **100%는 숫자 대신 ✕** (16px 폭에 세 자리는 물리적으로 안 들어간다)
- 재로그인은 회색 배경 + `!`
- 갱신 실패(STALE)는 아이콘 전체를 흐리게(알파 45%)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_icon_render.py`:

```python
from datetime import datetime, timedelta, timezone

from claude_usage_overlay.icon_render import render_icon
from claude_usage_overlay.models import HudState, Status, UsageSnapshot

NOW = datetime(2026, 8, 10, 3, 25, tzinfo=timezone.utc)


def state(status, pct=23.0):
    snap = (
        None
        if pct is None
        else UsageSnapshot(pct, NOW + timedelta(hours=2), 15.0, NOW)
    )
    return HudState(status, snap, "")


ICON = 16  # 테스트는 배율에 흔들리지 않도록 항상 크기를 명시한다


def test_icon_is_requested_size_and_rgba():
    img = render_icon(state(Status.OK), size=ICON)
    assert img.size == (ICON, ICON)
    assert img.mode == "RGBA"


def test_renders_at_high_dpi_sizes_too():
    """배율 125%·150% PC에서는 트레이 아이콘이 20px·24px이다."""
    for size in (20, 24, 32):
        img = render_icon(state(Status.OK, 23.0), size=size)
        assert img.size == (size, size)


def test_default_size_follows_system_metric():
    from claude_usage_overlay import winmetrics

    img = render_icon(state(Status.OK, 23.0))
    assert img.size == (winmetrics.system_icon_size(),) * 2


def test_low_usage_fills_bottom_with_green():
    img = render_icon(state(Status.OK, 23.0), size=ICON)
    r, g, b, a = img.getpixel((1, 15))       # 바닥 왼쪽 — 채움 영역
    assert g > r and g > b, "바닥은 초록이어야 한다"
    r2, g2, b2, _ = img.getpixel((1, 1))     # 꼭대기 — 빈 영역
    assert g2 < 120, "꼭대기는 어두운 배경이어야 한다"


def test_warn_band_fills_yellow():
    img = render_icon(state(Status.OK, 75.0), size=ICON)
    r, g, b, _ = img.getpixel((1, 15))
    assert r > 200 and g > 150 and b < 150, "주의 구간은 노랑이어야 한다"


def test_danger_band_fills_red():
    img = render_icon(state(Status.OK, 95.0), size=ICON)
    r, g, b, _ = img.getpixel((1, 15))
    assert r > 200 and g < 180, "위험 구간은 빨강이어야 한다"


def test_fill_height_grows_with_usage():
    def filled_rows(pct):
        img = render_icon(state(Status.OK, pct), size=ICON)
        rows = 0
        for y in range(ICON):
            r, g, b, _ = img.getpixel((1, y))
            if r + g + b > 200:              # 배경보다 밝으면 채워진 것
                rows += 1
        return rows

    assert filled_rows(90.0) > filled_rows(20.0)


def test_full_usage_draws_no_digits():
    """100%는 ✕로 대체된다. 숫자가 들어갈 자리가 없다."""
    full = render_icon(state(Status.OK, 100.0), size=ICON)
    partial = render_icon(state(Status.OK, 23.0), size=ICON)
    assert full.tobytes() != partial.tobytes()
    # 배경이 전부 빨강 계열인지 — 모서리 안쪽을 확인
    r, g, b, _ = full.getpixel((2, 2))
    assert r > 200 and g < 180


def test_relogin_uses_grey_background():
    img = render_icon(HudState(Status.RELOGIN, None, "재로그인 필요"), size=ICON)
    r, g, b, _ = img.getpixel((8, 3))
    assert abs(r - g) < 30 and abs(g - b) < 30, "회색이어야 한다"


def test_stale_is_dimmed():
    normal = render_icon(state(Status.OK, 23.0), size=ICON)
    stale = render_icon(state(Status.STALE, 23.0), size=ICON)
    assert stale.getpixel((1, 15))[3] < normal.getpixel((1, 15))[3]


def test_schema_error_renders_without_crashing():
    img = render_icon(HudState(Status.SCHEMA_ERROR, None, "형식 변경"), size=ICON)
    assert img.size == (ICON, ICON)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_icon_render.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claude_usage_overlay.icon_render'`

- [ ] **Step 3: `claude_usage_overlay/icon_render.py` 작성**

```python
"""HudState → 16×16 트레이 아이콘. 순수 함수라 UI 없이 테스트할 수 있다.

수위 경계에서 숫자 색을 반전시킨다. PIL에는 클리핑이 없으므로
밝은 글자 레이어와 어두운 글자 레이어를 따로 그린 뒤 수위선을 기준으로
잘라 합성한다.
"""

from PIL import Image, ImageDraw, ImageFont

from . import theme, winmetrics
from .models import HudState, Status

FONT_FILES = ["segoeuib.ttf", "arialbd.ttf"]
STALE_ALPHA = 115  # 255의 약 45%


def _hex(color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    color = color.lstrip("#")
    return (int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16), alpha)


def _font(size: int):
    for name in FONT_FILES:
        try:
            return ImageFont.truetype(str(winmetrics.fonts_dir() / name), size)
        except OSError:
            continue
    return ImageFont.load_default()


def _centered_text(size: int, text: str, color: str) -> Image.Image:
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    font = _font(max(8, int(size * 0.70)))
    box = draw.textbbox((0, 0), text, font=font)
    x = (size - (box[2] - box[0])) / 2 - box[0]
    y = (size - (box[3] - box[1])) / 2 - box[1]
    draw.text((x, y), text, font=font, fill=_hex(color))
    return layer


def _base(size: int, bg: str) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle(
        [(0, 0), (size - 1, size - 1)], radius=max(2, size // 5), fill=_hex(bg)
    )
    return img


def _symbol_icon(size: int, bg: str, text: str, fg: str) -> Image.Image:
    img = _base(size, bg)
    return Image.alpha_composite(img, _centered_text(size, text, fg))


def _cross_icon(size: int, bg: str) -> Image.Image:
    img = _base(size, bg)
    draw = ImageDraw.Draw(img)
    pad = size * 0.31
    width = max(2, size // 8)
    draw.line([(pad, pad), (size - pad, size - pad)], fill=_hex("#2a0d0d"), width=width)
    draw.line([(size - pad, pad), (pad, size - pad)], fill=_hex("#2a0d0d"), width=width)
    return img


def _dim(img: Image.Image) -> Image.Image:
    alpha = img.getchannel("A").point(lambda v: min(v, STALE_ALPHA))
    img.putalpha(alpha)
    return img


def render_icon(
    state: HudState, size: int | None = None, warn: int = 70, danger: int = 90
) -> Image.Image:
    # 배율 100%면 16, 150%면 24. 하드코딩하지 않는다.
    size = size or winmetrics.system_icon_size()

    if state.status is Status.RELOGIN:
        return _symbol_icon(size, theme.GREY, "!", theme.RED)

    if state.snapshot is None:
        return _symbol_icon(size, theme.GREY, "?", theme.TEXT_LIGHT)

    pct = max(0.0, min(100.0, state.snapshot.five_hour_pct))
    fill_color = theme.color_for(pct, warn, danger)

    if pct >= 100:
        img = _cross_icon(size, fill_color)
        return _dim(img) if state.status is Status.STALE else img

    # 배경 + 아래에서 차오르는 채움
    img = _base(size, theme.BG)
    fill_top = size - round(size * pct / 100.0)
    if fill_top < size:
        fill_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(fill_layer).rounded_rectangle(
            [(0, 0), (size - 1, size - 1)], radius=max(2, size // 5), fill=_hex(fill_color)
        )
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).rectangle([(0, fill_top), (size, size)], fill=255)
        img.paste(fill_layer, (0, 0), mask)

    # 숫자를 두 번 그리고 수위선에서 잘라 합친다
    text = str(int(round(pct)))
    light = _centered_text(size, text, theme.TEXT_LIGHT)
    dark = _centered_text(size, text, theme.TEXT_DARK)

    above = Image.new("L", (size, size), 0)
    ImageDraw.Draw(above).rectangle([(0, 0), (size, fill_top)], fill=255)
    below = Image.new("L", (size, size), 0)
    ImageDraw.Draw(below).rectangle([(0, fill_top), (size, size)], fill=255)

    img.paste(light, (0, 0), Image.composite(light.getchannel("A"), above.point(lambda _: 0), above))
    img.paste(dark, (0, 0), Image.composite(dark.getchannel("A"), below.point(lambda _: 0), below))

    return _dim(img) if state.status is Status.STALE else img
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_icon_render.py -v`
Expected: PASS (11 passed)

픽셀 단언이 실패하면 아래 스크립트로 실제 아이콘을 눈으로 확인한 뒤 좌표를 조정한다. **테스트를 지우지 말고 좌표를 고친다.**

```bash
python -c "from datetime import datetime,timedelta,timezone; from claude_usage_overlay.icon_render import render_icon; from claude_usage_overlay.models import *; n=datetime.now(timezone.utc); render_icon(HudState(Status.OK, UsageSnapshot(23.0,n+timedelta(hours=2),15.0,n), ''), size=16).resize((160,160), 0).save('icon-preview.png')"
```

- [ ] **Step 5: 커밋**

```bash
git add claude_usage_overlay/icon_render.py tests/test_icon_render.py
git commit -m "feat: 수위 반전 숫자 트레이 아이콘 렌더러 추가"
```

---

### Task 10: 오버레이 창

**Files:**
- Create: `claude_usage_overlay/overlay.py`

**Interfaces:**
- Consumes: `models.HudState`, `models.Status`, `theme.*`, `formatting.format_countdown`, `formatting.format_age`, `config.Config`, `config.save_config`, `winmetrics.dpi_scale`, `winmetrics.virtual_screen_rect`, `winmetrics.is_position_visible`
- Produces: `Overlay(root: tkinter.Tk, config: Config)`,
  메서드 `update(state: HudState) -> None`, `show() -> None`, `hide() -> None`, `is_visible() -> bool`

**확정 사항:** 링 게이지 + 텍스트 2줄. 무테두리 · 반투명(alpha 0.82) · 항상 위 · 드래그 이동. 창 위치는 드래그를 놓을 때 설정에 저장한다.

**이식성 요구 두 가지:**

1. 모든 치수와 글꼴 크기에 `winmetrics.dpi_scale()`을 곱한다. 배율 150% PC에서 창이 절반 크기로 보이면 안 된다.
2. 저장된 위치가 지금 화면에 없으면 기본 위치로 되돌린다. 보조 모니터에 창을 두고 케이블을 뽑으면 창을 되찾을 방법이 없어지기 때문이다.

**1초마다 다시 그리지만 네트워크는 건드리지 않는다.** 카운트다운은 `resets_at`에서 로컬 계산한다.

UI라 자동 테스트하지 않는다. Step 4의 수동 검증 목록으로 확인한다.

- [ ] **Step 1: `claude_usage_overlay/overlay.py` 작성**

```python
"""tkinter 오버레이 창.

1초마다 다시 그리지만 네트워크는 부르지 않는다. 카운트다운은
resets_at에서 로컬로 계산한다. 화면은 매초 살아 움직이고 API는 5분에 한 번만.

모든 치수는 기준값 × DPI 배율이다. 배율 150% PC에서도 같은 크기로 보인다.
"""

import tkinter as tk
from datetime import datetime, timezone

from . import theme
from .config import Config, save_config
from .formatting import format_age, format_countdown
from .models import HudState, Status
from .winmetrics import dpi_scale, is_position_visible, virtual_screen_rect

BASE_WIDTH, BASE_HEIGHT = 186, 62
BASE_RING_BOX = (12, 12, 54, 54)   # x0, y0, x1, y1
BASE_RING_WIDTH = 5
BASE_TEXT_X = 66
BASE_LINE1_Y, BASE_LINE2_Y = 24, 40
MARGIN = 24
ALPHA = 0.82


class Overlay:
    def __init__(self, root: tk.Tk, config: Config) -> None:
        self._config = config
        self._scale = dpi_scale()

        s = self._scale
        self._w = round(BASE_WIDTH * s)
        self._h = round(BASE_HEIGHT * s)
        self._ring = tuple(round(v * s) for v in BASE_RING_BOX)
        self._ring_width = max(3, round(BASE_RING_WIDTH * s))
        self._text_x = round(BASE_TEXT_X * s)
        self._line1_y = round(BASE_LINE1_Y * s)
        self._line2_y = round(BASE_LINE2_Y * s)
        self._font_pct = ("Segoe UI", max(8, round(10 * s)), "bold")
        self._font_line1 = ("Segoe UI", max(7, round(9 * s)))
        self._font_line2 = ("Segoe UI", max(6, round(8 * s)))

        self._win = tk.Toplevel(root)
        self._win.overrideredirect(True)          # 테두리 제거
        self._win.attributes("-topmost", True)    # 항상 위
        self._win.attributes("-alpha", ALPHA)     # 반투명
        self._win.configure(bg=theme.BG)

        x, y = self._initial_position(root)
        self._win.geometry(f"{self._w}x{self._h}+{x}+{y}")

        self._canvas = tk.Canvas(
            self._win, width=self._w, height=self._h, bg=theme.BG, highlightthickness=0
        )
        self._canvas.pack()

        self._drag = {"x": 0, "y": 0}
        for widget in (self._win, self._canvas):
            widget.bind("<Button-1>", self._on_press)
            widget.bind("<B1-Motion>", self._on_drag)
            widget.bind("<ButtonRelease-1>", self._on_release)

        self._state = HudState(Status.STALE, None, "불러오는 중")
        if not config.overlay_visible:
            self._win.withdraw()
        self._tick()

    # --- 공개 인터페이스 -------------------------------------------------

    def update(self, state: HudState) -> None:
        self._state = state

    def show(self) -> None:
        self._win.deiconify()
        self._config.overlay_visible = True
        save_config(self._config)

    def hide(self) -> None:
        self._win.withdraw()
        self._config.overlay_visible = False
        save_config(self._config)

    def is_visible(self) -> bool:
        return self._win.state() != "withdrawn"

    # --- 위치 ------------------------------------------------------------

    def _initial_position(self, root: tk.Tk) -> tuple[int, int]:
        """저장된 위치를 쓰되, 지금 화면에 없으면 기본 위치로 되돌린다.

        보조 모니터에 창을 두고 케이블을 뽑으면 저장된 좌표가 아무 화면에도
        없는 영역을 가리킨다. 그대로 두면 창을 되찾을 방법이 없다.
        """
        if self._config.x is not None and self._config.y is not None:
            if is_position_visible(
                self._config.x, self._config.y, self._w, self._h, virtual_screen_rect()
            ):
                return self._config.x, self._config.y

        return root.winfo_screenwidth() - self._w - MARGIN, MARGIN

    # --- 드래그 이동 ------------------------------------------------------

    def _on_press(self, event) -> None:
        self._drag["x"] = event.x_root - self._win.winfo_x()
        self._drag["y"] = event.y_root - self._win.winfo_y()

    def _on_drag(self, event) -> None:
        self._win.geometry(
            f"+{event.x_root - self._drag['x']}+{event.y_root - self._drag['y']}"
        )

    def _on_release(self, _event) -> None:
        self._config.x = self._win.winfo_x()
        self._config.y = self._win.winfo_y()
        save_config(self._config)

    # --- 그리기 ----------------------------------------------------------

    def _tick(self) -> None:
        self._redraw()
        self._win.after(1000, self._tick)

    def _redraw(self) -> None:
        c = self._canvas
        c.delete("all")
        state = self._state
        now = datetime.now(timezone.utc)

        if state.status is Status.RELOGIN:
            self._draw_ring(0, theme.GREY)
            self._draw_text("재로그인 필요", theme.RED, "claude auth login", "#8b8b93")
            return

        if state.snapshot is None:
            self._draw_ring(0, theme.GREY)
            self._draw_text(state.detail or "불러오는 중", "#8b8b93", "", "#8b8b93")
            return

        snap = state.snapshot
        pct = snap.five_hour_pct
        color = theme.color_for(pct, self._config.warn_pct, self._config.danger_pct)
        dim = state.status is Status.STALE

        self._draw_ring(pct, "#3a3f4b" if dim else color)
        c.create_text(
            (self._ring[0] + self._ring[2]) / 2,
            (self._ring[1] + self._ring[3]) / 2,
            text=f"{int(round(pct))}%",
            fill="#6d7280" if dim else theme.TEXT_LIGHT,
            font=self._font_pct,
        )

        line1 = format_countdown(snap.resets_at, now)
        if state.status is Status.STALE:
            line2, line2_color = state.detail, theme.YELLOW
        elif state.status is Status.RATE_LIMITED:
            line2, line2_color = "호출 한도 — 잠시 후 재시도", theme.YELLOW
        else:
            line2, line2_color = format_age(snap.fetched_at, now), "#8b8b93"

        self._draw_text(line1, "#6d7280" if dim else theme.TEXT_LIGHT, line2, line2_color)

    def _draw_ring(self, pct: float, color: str) -> None:
        x0, y0, x1, y1 = self._ring
        self._canvas.create_arc(
            x0, y0, x1, y1, start=0, extent=359.9, style=tk.ARC,
            outline="#333845", width=self._ring_width,
        )
        if pct > 0:
            self._canvas.create_arc(
                x0, y0, x1, y1, start=90, extent=-max(1.0, 359.9 * pct / 100.0),
                style=tk.ARC, outline=color, width=self._ring_width,
            )

    def _draw_text(self, line1: str, color1: str, line2: str, color2: str) -> None:
        self._canvas.create_text(
            self._text_x, self._line1_y, text=line1, anchor="w",
            fill=color1, font=self._font_line1,
        )
        if line2:
            self._canvas.create_text(
                self._text_x, self._line2_y, text=line2, anchor="w",
                fill=color2, font=self._font_line2,
            )
```

- [ ] **Step 2: 임시 확인 스크립트로 창을 띄워본다**

`scratch_overlay.py` (커밋하지 않는다):

```python
import tkinter as tk
from datetime import datetime, timedelta, timezone

from claude_usage_overlay.config import Config
from claude_usage_overlay.models import HudState, Status, UsageSnapshot
from claude_usage_overlay.overlay import Overlay

root = tk.Tk()
root.withdraw()
now = datetime.now(timezone.utc)
ov = Overlay(root, Config())
ov.update(
    HudState(
        Status.OK,
        UsageSnapshot(23.0, now + timedelta(hours=2, minutes=14), 15.0, now),
        "",
    )
)
root.mainloop()
```

Run: `python scratch_overlay.py`

- [ ] **Step 3: 수동 검증 목록**

각 항목을 눈으로 확인한다.

- [ ] 창에 테두리와 제목 표시줄이 없다
- [ ] 반투명하게 뒤가 비친다
- [ ] 다른 창을 클릭해도 위에 남아 있다
- [ ] 드래그로 옮겨진다
- [ ] 링이 23%만큼 채워져 있고 초록색이다
- [ ] 가운데 `23%`, 오른쪽에 `2시간 14분 후 리셋`, `방금 갱신됨`
- [ ] 카운트다운 분이 실제로 줄어든다 (1분 기다려 확인)
- [ ] 스크립트에서 `23.0`을 `75.0`, `95.0`으로 바꾸면 링이 노랑, 빨강이 된다
- [ ] `Status.STALE`로 바꾸면 링과 글자가 흐려지고 두 번째 줄이 노란 경고로 바뀐다
- [ ] `Status.RELOGIN`으로 바꾸면 "재로그인 필요 / claude auth login"이 표시된다

이식성 확인 두 가지:

- [ ] `Config(x=99999, y=99999)`로 띄우면 화면 밖이 아니라 **오른쪽 위 기본 위치**에 뜬다
- [ ] Windows 설정에서 배율을 150%로 바꾸고 로그아웃/로그인 후 다시 띄우면, 창과 글자가 100%일 때와 **같은 물리적 크기**로 보인다 (확인 후 배율을 원래대로 되돌린다)

- [ ] **Step 4: 확인 스크립트 삭제 후 커밋**

```bash
rm scratch_overlay.py
git add claude_usage_overlay/overlay.py
git commit -m "feat: 링 게이지 오버레이 창 추가"
```

---

### Task 11: 트레이 아이콘과 자동 시작

**Files:**
- Create: `claude_usage_overlay/autostart.py`
- Create: `claude_usage_overlay/tray.py`
- Test: `tests/test_autostart.py`

**Interfaces:**
- Consumes: `icon_render.render_icon`, `models.HudState`, `models.Status`, `formatting.*`, `poller.Poller`, `overlay.Overlay`, `config.*`
- Produces:
  - `autostart.build_command() -> str`, `autostart.is_enabled() -> bool`, `autostart.enable() -> None`, `autostart.disable() -> None`, 상수 `RUN_KEY`, `VALUE_NAME`
  - `tray.Tray(poller, overlay, config)`, 메서드 `run() -> None`, `refresh_icon() -> None`, `stop() -> None`

**툴팁 내용 (스펙 확정):** 5시간 사용률 · 리셋 카운트다운 · 7일 사용률 · 갱신 시각
**메뉴:** 오버레이 숨기기/보이기 · 지금 갱신 · 시작할 때 자동 실행(체크) · 설정 파일 열기 · 종료

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_autostart.py`:

```python
import sys

from claude_usage_overlay import autostart


def test_command_runs_module_with_pythonw(monkeypatch):
    monkeypatch.setattr(sys, "executable", r"C:\Python312\python.exe")
    cmd = autostart.build_command()
    # 콘솔 창이 뜨지 않도록 pythonw를 쓴다
    assert "pythonw.exe" in cmd
    assert "-m claude_usage_overlay" in cmd
    assert cmd.startswith('"')          # 공백 있는 경로를 위해 따옴표로 감싼다


def test_command_handles_already_pythonw(monkeypatch):
    monkeypatch.setattr(sys, "executable", r"C:\Python312\pythonw.exe")
    assert autostart.build_command().count("pythonw.exe") == 1


def test_registry_constants_target_current_user():
    assert autostart.RUN_KEY == r"Software\Microsoft\Windows\CurrentVersion\Run"
    assert autostart.VALUE_NAME == "ClaudeUsageOverlay"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_autostart.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claude_usage_overlay.autostart'`

- [ ] **Step 3: `claude_usage_overlay/autostart.py` 작성**

```python
"""시작 프로그램 등록. HKCU만 건드린다 (관리자 권한 불필요)."""

import sys
import winreg

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "ClaudeUsageOverlay"


def build_command() -> str:
    """콘솔 창이 뜨지 않도록 pythonw.exe로 실행한다."""
    exe = sys.executable.replace("python.exe", "pythonw.exe")
    return f'"{exe}" -m claude_usage_overlay'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return bool(value)
    except OSError:
        return False


def enable() -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, build_command())


def disable() -> None:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, VALUE_NAME)
    except OSError:
        pass
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_autostart.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: `claude_usage_overlay/tray.py` 작성**

```python
"""pystray 트레이 아이콘과 메뉴."""

import os
import subprocess
from datetime import datetime, timezone

import pystray

from . import autostart
from .config import Config, config_path, save_config
from .formatting import format_age, format_countdown
from .icon_render import render_icon
from .models import HudState, Status


def _tooltip(state: HudState) -> str:
    if state.status is Status.RELOGIN:
        return "Claude 사용량\n재로그인 필요 — claude auth login"
    if state.snapshot is None:
        return f"Claude 사용량\n{state.detail or '불러오는 중'}"

    now = datetime.now(timezone.utc)
    snap = state.snapshot
    lines = [
        "Claude 사용량",
        f"5시간 창  {int(round(snap.five_hour_pct))}%  ·  {format_countdown(snap.resets_at, now)}",
    ]
    if snap.seven_day_pct is not None:
        lines.append(f"7일 창  {int(round(snap.seven_day_pct))}%")
    lines.append(state.detail if state.status is Status.STALE else format_age(snap.fetched_at, now))
    return "\n".join(lines)


class Tray:
    def __init__(self, poller, overlay, config: Config) -> None:
        self._poller = poller
        self._overlay = overlay
        self._config = config
        self._icon = pystray.Icon(
            "claude-usage-overlay",
            icon=render_icon(poller.state(), warn=config.warn_pct, danger=config.danger_pct),
            title=_tooltip(poller.state()),
            menu=self._build_menu(),
        )

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(
                lambda _: "오버레이 숨기기" if self._overlay.is_visible() else "오버레이 보이기",
                self._toggle_overlay,
            ),
            pystray.MenuItem("지금 갱신", self._refresh_now),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "시작할 때 자동 실행",
                self._toggle_autostart,
                checked=lambda _: autostart.is_enabled(),
            ),
            pystray.MenuItem("설정 파일 열기", self._open_config),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("종료", self._quit),
        )

    # --- 메뉴 동작 --------------------------------------------------------

    def _toggle_overlay(self) -> None:
        self._overlay.hide() if self._overlay.is_visible() else self._overlay.show()

    def _refresh_now(self) -> None:
        self._poller.request_now()

    def _toggle_autostart(self) -> None:
        autostart.disable() if autostart.is_enabled() else autostart.enable()

    def _open_config(self) -> None:
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            save_config(self._config, path)
        subprocess.Popen(["notepad.exe", str(path)])

    def _quit(self) -> None:
        self._poller.stop()
        self._icon.stop()
        os._exit(0)

    # --- 공개 인터페이스 --------------------------------------------------

    def refresh_icon(self) -> None:
        state = self._poller.state()
        self._icon.icon = render_icon(
            state, warn=self._config.warn_pct, danger=self._config.danger_pct
        )
        self._icon.title = _tooltip(state)

    def run(self) -> None:
        """블로킹 호출. 별도 스레드에서 부른다."""
        self._icon.run()

    def stop(self) -> None:
        self._icon.stop()
```

- [ ] **Step 6: 의존성 설치 확인**

Run: `pip install pystray pillow`
Expected: 성공. 이미 설치돼 있으면 `Requirement already satisfied`

- [ ] **Step 7: 전체 테스트 실행**

Run: `python -m pytest -v`
Expected: PASS

- [ ] **Step 8: 커밋**

```bash
git add claude_usage_overlay/autostart.py claude_usage_overlay/tray.py tests/test_autostart.py
git commit -m "feat: 트레이 아이콘과 시작 프로그램 등록 추가"
```

---

### Task 12: 통합 진입점

**Files:**
- Create: `claude_usage_overlay/__main__.py`
- Create: `README.md`

**Interfaces:**
- Consumes: 앞선 모든 모듈
- Produces: `python -m claude_usage_overlay`로 실행되는 프로그램

**스레드 배치:** tkinter는 메인 스레드에서만 건드린다. 폴러는 자기 스레드에서 돌고, pystray도 자기 스레드에서 돈다. 메인 스레드는 tkinter `after` 루프로 1초마다 폴러 상태를 읽어 오버레이와 트레이에 전달한다.

- [ ] **Step 1: `claude_usage_overlay/__main__.py` 작성**

```python
"""진입점.

스레드 배치:
  메인 스레드   tkinter (오버레이) + 1초마다 상태 펌프
  폴러 스레드   5분마다 API 조회
  트레이 스레드 pystray 이벤트 루프

tkinter는 메인 스레드에서만 건드린다. 폴러는 잠금으로 보호된 state()만 노출한다.
"""

import threading
import tkinter as tk

from .config import load_config
from .credentials import CredentialStore
from .overlay import Overlay
from .poller import Poller
from .tray import Tray

PUMP_INTERVAL_MS = 1000


def main() -> None:
    config = load_config()

    poller = Poller(store=CredentialStore(), config=config)
    poller.start()

    root = tk.Tk()
    root.withdraw()  # 보이지 않는 루트. 실제 창은 Overlay가 만드는 Toplevel이다

    overlay = Overlay(root, config)
    tray = Tray(poller, overlay, config)

    threading.Thread(target=tray.run, daemon=True).start()

    def pump() -> None:
        state = poller.state()
        overlay.update(state)
        tray.refresh_icon()
        root.after(PUMP_INTERVAL_MS, pump)

    root.after(PUMP_INTERVAL_MS, pump)
    root.mainloop()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 실행해서 동작 확인**

Run: `python -m claude_usage_overlay`

- [ ] **Step 3: 통합 수동 검증 목록**

- [ ] 오버레이가 화면 오른쪽 위에 뜬다
- [ ] 링에 실제 사용률이 표시된다 (`claude auth status`로 로그인 상태 확인)
- [ ] 트레이에 아이콘이 생기고 숫자가 보인다
- [ ] 트레이 아이콘에 마우스를 올리면 5시간·7일·갱신 시각이 툴팁으로 나온다
- [ ] 오른쪽 클릭 메뉴가 열린다
- [ ] "오버레이 숨기기"로 창이 사라지고, 메뉴 문구가 "오버레이 보이기"로 바뀐다
- [ ] "지금 갱신"을 누르면 몇 초 안에 갱신 시각이 "방금 갱신됨"으로 바뀐다
- [ ] 오버레이를 드래그해 옮기고 프로그램을 재시작하면 그 위치에 뜬다
- [ ] "종료"로 프로세스가 완전히 끝난다 (작업 관리자에서 pythonw 확인)

- [ ] **Step 4: 실패 상황 수동 검증**

- [ ] 인터넷을 끊고 5분 이상 두면 링이 흐려지고 "N분째 갱신 실패"가 뜬다
- [ ] 인터넷을 복구하면 다음 조회에서 정상으로 돌아온다
- [ ] `%USERPROFILE%\.claude\.credentials.json`을 잠시 다른 이름으로 옮기면 "재로그인 필요"가 뜬다 (확인 후 반드시 되돌린다)

- [ ] **Step 5: `README.md` 작성**

```markdown
# Claude Usage Overlay

Claude 사용량(5시간 창)을 Windows 화면에 항상 띄우는 상주 프로그램.

## 필요 조건

- Windows, Python 3.12
- 터미널에서 `claude auth login`이 완료된 상태

## 설치

```bash
pip install pystray pillow
```

## 실행

```bash
python -m claude_usage_overlay
```

트레이 메뉴의 "시작할 때 자동 실행"을 켜면 로그인 시 자동으로 뜬다.

## 설정

`%APPDATA%\claude-usage-overlay\config.json` — 트레이 메뉴의 "설정 파일 열기"로도 열 수 있다.

| 키 | 기본값 | 설명 |
|---|---|---|
| `poll_seconds` | 300 | 조회 주기(초). 최소 60 |
| `warn_pct` | 70 | 노란색으로 바뀌는 사용률 |
| `danger_pct` | 90 | 빨간색으로 바뀌는 사용률 |
| `x`, `y` | 없음 | 오버레이 위치. 드래그하면 자동 저장 |

## 주의

사용량 엔드포인트는 문서화된 공개 API가 아니다. 예고 없이 바뀔 수 있고, 그때는
숫자를 지어내는 대신 "응답 형식이 바뀌었습니다"를 표시한다.

30일 넘게 이 프로그램과 Claude Code를 모두 쓰지 않으면 refreshToken이 만료되어
`claude auth login`을 다시 해야 한다.

## 테스트

```bash
pip install pytest
python -m pytest -v
```
```

- [ ] **Step 6: 전체 테스트 실행**

Run: `python -m pytest -v`
Expected: PASS

- [ ] **Step 7: 커밋**

```bash
git add claude_usage_overlay/__main__.py README.md
git commit -m "feat: 통합 진입점과 README 추가"
```

---

## 구현 후 확인할 미해결 사항

스펙 12장의 항목들이다. 구현이 끝난 뒤 처리한다.

- [ ] **엔드포인트 호출 한도 실측** — 5분 주기는 안전하다고 판단해 고른 값이지 측정값이 아니다. 프로그램을 몇 시간 켜두고 429가 한 번도 안 나오는지 확인한다. 나오면 `poll_seconds`를 올린다.
- [ ] **`client_id` 안정성** — 갱신이 400/401로 실패하면 `client_id` 변경을 의심한다. `credentials.py`의 `ReloginRequired` 메시지에 상태 코드가 들어 있으므로 진단할 수 있다.
- [ ] **스키마 변경 감지** — `SCHEMA_ERROR` 상태가 뜨면 `/api/oauth/usage` 응답을 직접 확인하고 `usage_client.py`의 파싱을 고친다.
- [ ] **고배율 환경 실검증** — `winmetrics`로 배율을 흡수하도록 짰지만, 실제로 150% PC에서 돌려본 것은 아니다. 배율을 바꿔 한 번 확인한다. tkinter가 DPI를 어떻게 처리하느냐에 따라 `dpi_scale()`을 곱하는 것이 이중 확대가 될 수 있다 — 그 경우 창이 지나치게 커지므로 바로 눈에 띈다.
