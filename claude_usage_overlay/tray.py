"""pystray 트레이 아이콘과 메뉴."""

import os
import subprocess
import threading
from datetime import datetime, timezone

import pystray

from . import autostart, font_install
from .config import Config, config_path, save_config
from .formatting import format_age, format_countdown
from .icon_render import render_icon
from .models import HudState, Status
from .winmetrics import system_icon_size


STALE_STATUSES = frozenset({Status.STALE, Status.RATE_LIMITED})

# Win32 Shell_NotifyIcon의 szTip은 128 wchar 고정 버퍼다. pystray가 문자열을
# 그대로 구조체에 넣으므로 129자에서 `ValueError: string too long`이 난다.
# 그 예외는 refresh_icon()을 부르는 메인 스레드의 pump() 안에서 터져 다음
# root.after 예약을 막고 상태 갱신을 통째로 멈춘다 — pythonw에는 콘솔이
# 없어 원인도 안 남는다. 문구는 우리가 고정 상수로 통제하지만(credentials가
# 예외 텍스트를 붙이지 않는다), 마지막 방어를 여기 둔다.
TOOLTIP_LIMIT = 128


def _clip(text: str) -> str:
    if len(text) <= TOOLTIP_LIMIT:
        return text
    return text[: TOOLTIP_LIMIT - 1] + "…"


def _load_icon_at(image, size: int) -> int:
    """이미지를 정확히 size 픽셀짜리 HICON으로 만든다.

    pystray가 기본으로 하는 일은 이렇다.

        LoadImage(..., IMAGE_ICON, 0, 0, LR_DEFAULTSIZE)

    LR_DEFAULTSIZE는 "큰 아이콘 크기(SM_CXICON, 100%에서 32px)로 로드"라는
    뜻이다. 트레이가 쓰는 것은 작은 아이콘 크기(16px)인데도 그렇다. 그래서
    16px 그림이 32px로 늘어났다가 화면에서 다시 16px로 줄어들고, 그 왕복에서
    숫자 획이 뭉개진다 — 흐리게 보이던 원인이다.

    크기를 명시하면 확대도 축소도 일어나지 않고 우리가 그린 픽셀이 그대로 간다.
    """
    from pystray._util import serialized_image, win32

    with serialized_image(image, "ICO") as path:
        handle = win32.LoadImage(
            None, path, win32.IMAGE_ICON, size, size, win32.LR_LOADFROMFILE
        )
    if not handle:
        raise OSError("LoadImage가 아이콘을 만들지 못했습니다")
    return handle


class _SharpIcon(pystray.Icon):
    """확대를 거치지 않고 아이콘을 싣는 트레이 아이콘.

    pystray의 내부 메서드를 갈아끼우므로 판올림에서 구조가 바뀔 수 있다.
    그때는 원래 방식으로 돌아간다 — 아이콘이 흐려질 뿐 프로그램은 돈다.
    """

    def _assert_icon_handle(self):
        if self._icon_handle:
            return
        try:
            self._icon_handle = _load_icon_at(self.icon, system_icon_size())
        except Exception:
            super()._assert_icon_handle()


def icon_key(state: HudState) -> tuple:
    """아이콘 그림이 달라지는 조건. 이 값이 그대로면 다시 그릴 필요가 없다.

    사용률은 반올림한 정수만 그림에 나타난다. 23.0%와 23.4%는 같은 그림이다.
    """
    if state.snapshot is None:
        return (state.status, None)
    return (state.status, round(state.snapshot.five_hour_pct))


def _tooltip(state: HudState) -> str:
    if state.snapshot is None:
        # RELOGIN·SCHEMA_ERROR 모두 여기로 온다. 문구는 만든 쪽이 정한다.
        return _clip(f"Claude 사용량\n{state.detail or '불러오는 중'}")

    now = datetime.now(timezone.utc)
    snap = state.snapshot
    lines = [
        "Claude 사용량",
        f"5시간 창  {int(round(snap.five_hour_pct))}%  ·  {format_countdown(snap.resets_at, now)}",
    ]
    if snap.seven_day_pct is not None:
        lines.append(f"7일 창  {int(round(snap.seven_day_pct))}%")
    lines.append(
        state.detail if state.status in STALE_STATUSES else format_age(snap.fetched_at, now)
    )
    return _clip("\n".join(lines))


class Tray:
    def __init__(self, poller, overlay, config: Config) -> None:
        self._poller = poller
        self._overlay = overlay
        self._config = config

        state = poller.state()
        self._icon_key = icon_key(state)
        self._title = _tooltip(state)
        self._icon = _SharpIcon(
            "claude-usage-overlay",
            icon=self._render(state),
            title=self._title,
            menu=self._build_menu(),
        )

    def _render(self, state: HudState):
        """트레이가 실제로 그리는 크기 그대로 만든다.

        _SharpIcon이 이 크기로 로드하므로 확대도 축소도 없다. 16px에 맞춰
        고른 글자 크기와 획이 화면까지 그대로 간다.
        """
        return render_icon(
            state,
            size=system_icon_size(),
            warn=self._config.warn_pct,
            danger=self._config.danger_pct,
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
            # 이미 깔려 있는 사람에게는 보일 이유가 없는 항목이다.
            pystray.MenuItem(
                "Pretendard 글꼴 설치",
                self._install_font,
                visible=lambda _: not font_install.is_installed(),
            ),
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

    def _install_font(self) -> None:
        """47MB를 받는 일이라 메뉴 콜백을 붙들고 있으면 안 된다.

        pystray 스레드가 여기서 막히면 메뉴가 닫히지 않고 트레이 아이콘도
        응답하지 않는다. 별도 스레드로 넘기고 결과만 풍선 알림으로 알린다.
        """
        threading.Thread(target=self._install_font_now, daemon=True).start()

    def _install_font_now(self) -> None:
        try:
            font_install.install()
        except Exception as err:  # 네트워크 실패·형식 변경 등
            self._notify(f"글꼴 설치 실패 — {type(err).__name__}")
            return
        self._notify("Pretendard 설치됨 — 다시 실행하면 적용됩니다")

    def _notify(self, message: str) -> None:
        """풍선 알림. 안 되는 환경이면 조용히 넘어간다."""
        try:
            self._icon.notify(message, "Claude 사용량")
        except Exception:
            pass

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
        """메인 스레드가 1초마다 부른다. **실제로 바뀐 것만 밀어 넣는다.**

        pystray의 Win32 백엔드는 icon·title 세터마다 HICON을 새로 만들고
        Shell_NotifyIcon을 부른다. 무조건 갱신하면 하루 86,400회다.
        """
        state = self._poller.state()

        key = icon_key(state)
        if key != self._icon_key:
            self._icon_key = key
            self._icon.icon = self._render(state)

        # 툴팁은 카운트다운과 갱신 시각 때문에 그림보다 자주 바뀐다. 둘 다
        # 분 단위이고 분 경계가 서로 어긋나 있어 분당 두 번꼴이다 —
        # 30분에 60회. 1,800회보다는 훨씬 적으므로 비교는 제값을 한다.
        title = _tooltip(state)
        if title != self._title:
            self._title = title
            self._icon.title = title

    def run(self) -> None:
        """블로킹 호출. 별도 스레드에서 부른다."""
        self._icon.run()

    def stop(self) -> None:
        self._icon.stop()
