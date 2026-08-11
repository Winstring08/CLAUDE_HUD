"""설정창.

**닫을 때 한 번에 적용하고 취소는 없다.** 닫기 단추·제목줄 ✕·Esc가 모두 같은 일을
한다. 값들이 다시 고르면 그만인 것들이라 취소가 벌어줄 게 없고, ✕만 취소로 두면
실수로 통째로 잃는다.

적용은 공유 Config 객체를 고치는 것으로 끝난다. 폴러·오버레이·트레이가 매 틱 다시
읽으므로 재시작 안내가 필요 없다.

  색 기준     → 다음 다시 그리기 (1초 이내)
  조회 주기   → **다음 폴링 틱부터.** 자고 있는 대기를 깨우지 않는다 — 깨우면
                API를 한 번 더 부르게 되고 그게 429의 원인이다
  자동 실행·아이콘 고정 → 닫을 때 레지스트리에 쓴다. **Config에는 저장하지 않는다**

치수는 배율 100% 기준값이고 전부 dpi_scale()을 곱한다. 글꼴은 음수 픽셀로 준다 —
포인트로 주면 tk scaling이 이미 반영한 배율에 한 번 더 곱해져 150%에서 글자만
창을 넘는다. 오버레이가 겪은 그대로다 (overlay.fonts_for 주석).
"""

import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass
from typing import Callable

from . import autostart, theme, tray_promote
from .checkbox import Checkbox
from .config import PCT_MAX, PCT_MIN, PCT_STEP, Config, save_config
from .dropdown import POLL_CHOICES, Dropdown
from .slider import Slider
from .winmetrics import dark_title_bar, dpi_scale

BASE_WIDTH = 300
PAD = 16          # 창 안쪽 여백
ROW_GAP = 10      # 위젯 줄 사이
INDENT = 24       # 하위 항목 들여쓰기
FONT_PX = 13
HINT_FONT_PX = 11

PROMOTE_HINT_WIN11 = (
    "윈도우 제한으로 바로 반영되지 않습니다 — 다음 로그온부터 적용됩니다.\n"
    "지금 보려면 ∧를 눌러 아이콘을 작업 표시줄로 끌어다 놓으세요."
)
PROMOTE_HINT_WIN10 = (
    "이 윈도우 판올림에서는 프로그램이 고정할 수 없습니다.\n"
    "설정 > 작업 표시줄 > 작업 표시줄에 표시할 아이콘 선택에서 켜세요."
)


@dataclass
class Draft:
    """창이 열려 있는 동안 들고 있는 값. 닫을 때 커밋한다.

    autostart·promote는 **Config에 없는 값**이다. 진짜 상태가 레지스트리에 있으므로
    창을 열 때 거기서 읽고 닫을 때 거기에 쓴다 (스펙 4.3절).
    """

    overlay_visible: bool
    overlay_detailed: bool
    poll_seconds: int
    warn_pct: int
    danger_pct: int
    autostart: bool
    promote: bool


def draft_from(cfg: Config, autostart_on: bool, promote_on: bool) -> Draft:
    return Draft(
        overlay_visible=cfg.overlay_visible,
        overlay_detailed=cfg.overlay_detailed,
        poll_seconds=cfg.poll_seconds,
        warn_pct=cfg.warn_pct,
        danger_pct=cfg.danger_pct,
        autostart=autostart_on,
        promote=promote_on,
    )


def commit_draft(draft: Draft, cfg: Config) -> None:
    """초안을 공유 Config에 옮긴다. **레지스트리는 건드리지 않는다** —
    그쪽은 부작용이 있어서 순수 함수로 두려면 여기서 빠져야 한다."""
    cfg.overlay_visible = draft.overlay_visible
    cfg.overlay_detailed = draft.overlay_detailed
    cfg.poll_seconds = draft.poll_seconds
    cfg.warn_pct = draft.warn_pct
    cfg.danger_pct = draft.danger_pct


def warn_bounds() -> tuple[int, int]:
    """노란 슬라이더가 갈 수 있는 범위.

    상한이 PCT_MAX보다 한 칸 낮은 이유는 빨간이 갈 자리를 남겨야 하기 때문이다.
    실제 상한은 여기에 "빨간 − PCT_STEP"을 한 번 더 씌운 값이고, 그건 빨간이
    움직일 때마다 바뀌므로 위젯이 set_bounds로 갱신한다.
    """
    return (PCT_MIN, PCT_MAX - PCT_STEP)


def danger_bounds() -> tuple[int, int]:
    """빨간 슬라이더가 갈 수 있는 범위. 하한이 노란보다 정확히 한 칸 위다."""
    return (PCT_MIN + PCT_STEP, PCT_MAX)


class SettingsWindow:
    def __init__(self, root: tk.Tk, config: Config, on_change: Callable[[], None]) -> None:
        self._config = config
        self._on_change = on_change
        self._closed = False
        self._scale = s = dpi_scale()

        self._supported = tray_promote.is_supported()
        self._draft = draft_from(
            config,
            autostart_on=autostart.is_enabled(),
            promote_on=tray_promote.is_promoted() if self._supported else False,
        )

        self._win = tk.Toplevel(root)
        self._win.title("Claude 사용량 설정")
        self._win.resizable(False, False)
        self._win.configure(bg=theme.BG)
        self._win.protocol("WM_DELETE_WINDOW", self.close)
        self._win.bind("<Escape>", lambda _e: self.close())

        # 오버레이는 pick_font_family로 고르지만 여기서는 Tk 기본 해석에 맡긴다 —
        # 번들 Pretendard가 이미 올라와 있으므로 이름만 주면 잡히고, 못 잡히면
        # Tk가 조용히 기본 글꼴로 그린다. 창 폭을 아래에서 실제로 재므로
        # 어느 글꼴이 잡혀도 문구가 잘리지 않는다.
        family = "Pretendard"
        self._font = (family, -round(FONT_PX * s))
        self._hint_font = (family, -round(HINT_FONT_PX * s))

        self._body = tk.Frame(self._win, bg=theme.BG)
        self._body.pack(fill="both", expand=True,
                        padx=round(PAD * s), pady=round(PAD * s))
        self._build()
        self._size_to_content()
        self._darken_title_bar()

    # --- 공개 인터페이스 -------------------------------------------------

    def focus(self) -> None:
        self._win.deiconify()
        self._win.lift()
        self._win.focus_force()

    def sync(self) -> None:
        """밖에서 표시·모드가 바뀌었을 때 체크박스를 따라 갱신한다.

        **이게 없으면 닫는 순간 옛 값이 덮어쓴다.** 설정창이 떠 있는 동안 오버레이
        우클릭이나 트레이로 표시를 끄면 체크박스는 켜진 옛 값 그대로이고, 닫으면
        오버레이가 도로 나타난다. overlay_detailed도 똑같다 (스펙 4.4절).

        밖에서 바뀌는 값은 이 둘뿐이다 — 자동 실행과 아이콘 고정은 Config에 없고
        레지스트리가 진짜 상태다.

        트레이 스레드에서도 불릴 수 있으므로 after()로 메인 스레드에 넘긴다.
        """
        if self._closed:
            return
        self._win.after(0, self._sync_now)

    def close(self) -> None:
        """닫기 단추·제목줄 ✕·Esc가 모두 여기로 온다. 취소는 없다."""
        if self._closed:
            return
        self._closed = True

        commit_draft(self._draft, self._config)
        save_config(self._config)

        # 레지스트리는 **닫을 때** 쓴다. 체크하는 순간이 아니다 — 창을 열어보다
        # 만 사람의 시작 프로그램을 바꿔놓으면 안 된다.
        if self._draft.autostart != autostart.is_enabled():
            autostart.enable() if self._draft.autostart else autostart.disable()
        if self._supported and self._draft.promote != tray_promote.is_promoted():
            tray_promote.promote(self._draft.promote)

        self._win.destroy()
        self._on_change()

    # --- 내부 ------------------------------------------------------------

    def _sync_now(self) -> None:
        if self._closed:
            return
        self._draft.overlay_visible = self._config.overlay_visible
        self._draft.overlay_detailed = self._config.overlay_detailed
        self._visible_box.set_checked(self._draft.overlay_visible)
        self._detailed_box.set_checked(self._draft.overlay_detailed)
        self._detailed_box.set_enabled(self._draft.overlay_visible)

    def _darken_title_bar(self) -> None:
        """HWND는 창이 한 번 배치된 뒤에야 유효하므로 update_idletasks가 먼저다."""
        try:
            self._win.update_idletasks()
            hwnd = int(self._win.wm_frame(), 16)
        except (tk.TclError, ValueError):
            return
        dark_title_bar(hwnd)

    def _width(self) -> int:
        """가장 긴 문구에서 역산한다.

        스펙 14장은 300 × 430을 "한국어 문구 길이를 눈대중한 값"으로 남기고
        만들면서 역산하라고 적어뒀다. 상수로 박으면 글꼴이 바뀌거나 문구가
        길어질 때 조용히 잘린다 — 오버레이 창 폭에서 겪은 그대로다.
        """
        base = round(BASE_WIDTH * self._scale)
        font = tkfont.Font(root=self._win, family=self._font[0], size=self._font[1])
        hint = tkfont.Font(root=self._win, family=self._hint_font[0],
                           size=self._hint_font[1])
        widest = 0
        for text in ("작업 표시줄에 트레이 아이콘 고정", "시작할 때 자동 실행",
                     "노란색으로 바뀌는 사용률", "빨간색으로 바뀌는 사용률"):
            widest = max(widest, font.measure(text))
        for line in (PROMOTE_HINT_WIN11 + "\n" + PROMOTE_HINT_WIN10).splitlines():
            widest = max(widest, hint.measure(line) + round(INDENT * self._scale))
        # 체크박스 상자와 여백, 슬라이더 값 글자 자리를 더한다.
        return max(base, widest + round((PAD * 2 + 40) * self._scale))

    def _size_to_content(self) -> None:
        """높이는 내용에서 나온다. 상수로 박으면 문구가 한 줄 늘 때 잘린다."""
        self._win.update_idletasks()
        self._win.geometry(f"{self._width()}x{self._win.winfo_reqheight()}")

    def _separator(self) -> None:
        tk.Frame(self._body, bg=theme.RING_TRACK, height=max(1, round(self._scale))).pack(
            fill="x", pady=round(ROW_GAP * self._scale)
        )

    def _label(self, text: str, font, color: str, indent: int = 0) -> None:
        tk.Label(
            self._body, text=text, font=font, bg=theme.BG, fg=color,
            justify="left", anchor="w",
        ).pack(fill="x", padx=(round(indent * self._scale), 0))

    def _build(self) -> None:
        s = self._scale
        width = self._width() - round(PAD * 2 * s)

        def set_visible(on: bool) -> None:
            self._draft.overlay_visible = on
            # "자세히 보기"는 "오버레이 표시"의 하위 항목이라 표시를 끄면 같이 흐려진다.
            self._detailed_box.set_enabled(on)

        def set_detailed(on: bool) -> None:
            self._draft.overlay_detailed = on

        self._visible_box = Checkbox(
            self._body, "오버레이 표시", self._draft.overlay_visible,
            set_visible, s, self._font, width=width,
        )
        self._visible_box.widget().pack(fill="x")

        self._detailed_box = Checkbox(
            self._body, "자세히 보기", self._draft.overlay_detailed,
            set_detailed, s, self._font, indent=INDENT, width=width,
        )
        self._detailed_box.widget().pack(fill="x")
        self._detailed_box.set_enabled(self._draft.overlay_visible)

        def set_autostart(on: bool) -> None:
            self._draft.autostart = on

        Checkbox(
            self._body, "시작할 때 자동 실행", self._draft.autostart,
            set_autostart, s, self._font, width=width,
        ).widget().pack(fill="x")

        def set_promote(on: bool) -> None:
            self._draft.promote = on

        promote_box = Checkbox(
            self._body, "작업 표시줄에 트레이 아이콘 고정", self._draft.promote,
            set_promote, s, self._font, width=width,
        )
        promote_box.widget().pack(fill="x")
        # 키가 없는 환경(Win10 등)에서는 체크박스가 비활성이고 아무것도 쓰지 않는다.
        promote_box.set_enabled(self._supported)
        self._label(
            PROMOTE_HINT_WIN11 if self._supported else PROMOTE_HINT_WIN10,
            self._hint_font, theme.TEXT_DIM, indent=INDENT,
        )

        self._separator()

        self._label("조회 주기", self._font, theme.TEXT_LIGHT)

        def set_poll(seconds: int) -> None:
            self._draft.poll_seconds = seconds

        poll = Dropdown(
            self._body, POLL_CHOICES, self._draft.poll_seconds, set_poll,
            s, self._font, width=round(110 * s),
        )
        poll.widget().pack(anchor="w", pady=(round(4 * s), 0))
        # **초안을 위젯이 실제로 고른 값으로 맞춘다.** 파일에 손으로 240초를 적어둔
        # 경우 드롭다운은 가장 가까운 5분을 보여주는데, 사용자가 그것을 건드리지
        # 않으면 set_poll이 안 불려 초안에는 240이 남는다. 그러면 화면은 "5분"인데
        # 저장되는 값은 240이 되어 다음에 열 때 또 같은 일이 벌어진다.
        # 슬라이더도 같은 이유로 _apply_slider_bounds가 값을 되받는다.
        self._draft.poll_seconds = poll.value()

        # **두 슬라이더의 트랙은 같은 구간(PCT_MIN~PCT_MAX)이다.** 서로를 넘지
        # 못하게 하는 것은 아래 _apply_slider_limits가 거는 한계뿐이다. 트랙까지
        # 좁히면 상대가 움직일 때 내 손잡이가 제자리에서 튄다 (slider 머리말).
        self._label("노란색으로 바뀌는 사용률", self._font, theme.TEXT_LIGHT)
        self._warn = Slider(
            self._body, width, PCT_MIN, PCT_MAX, PCT_STEP, self._draft.warn_pct,
            theme.YELLOW, self._set_warn, s, self._font,
        )
        self._warn.widget().pack(fill="x", pady=(0, round(ROW_GAP * s)))

        self._label("빨간색으로 바뀌는 사용률", self._font, theme.TEXT_LIGHT)
        self._danger = Slider(
            self._body, width, PCT_MIN, PCT_MAX, PCT_STEP, self._draft.danger_pct,
            theme.RED, self._set_danger, s, self._font,
        )
        self._danger.widget().pack(fill="x")
        self._apply_slider_limits()

        self._separator()

        row = tk.Frame(self._body, bg=theme.BG)
        row.pack(fill="x")
        tk.Label(
            row, text="닫으면 적용됩니다", font=self._hint_font,
            bg=theme.BG, fg=theme.TEXT_DIM,
        ).pack(side="left")
        tk.Button(
            row, text="닫기", command=self.close, font=self._font,
            bg=theme.RING_TRACK, fg=theme.TEXT_LIGHT,
            activebackground=theme.GREY, activeforeground=theme.TEXT_LIGHT,
            relief="flat", borderwidth=0, padx=round(14 * s), pady=round(4 * s),
        ).pack(side="right")

    def _set_warn(self, value: int) -> None:
        self._draft.warn_pct = value
        self._apply_slider_limits()

    def _set_danger(self, value: int) -> None:
        self._draft.danger_pct = value
        self._apply_slider_limits()

    def _apply_slider_limits(self) -> None:
        """서로를 넘지 않게 상대가 갈 수 있는 데까지를 갱신한다.

        **밀어내지 않는다** — 밀어내면 한쪽을 끌 때 다른 쪽이 따라와 값이 둘 다
        바뀐다. 손잡이가 그려지는 자리도 안 건드린다 (Slider.set_limits).
        """
        warn_lo, warn_hi = warn_bounds()
        danger_lo, danger_hi = danger_bounds()
        self._warn.set_limits(warn_lo, min(warn_hi, self._draft.danger_pct - PCT_STEP))
        self._danger.set_limits(max(danger_lo, self._draft.warn_pct + PCT_STEP), danger_hi)
        self._draft.warn_pct = self._warn.value()
        self._draft.danger_pct = self._danger.value()


# 열려 있는 창은 하나뿐이다. 두 곳(오버레이 우클릭·트레이 메뉴)에서 열리므로
# 모듈에 붙들어 둔다.
_current: SettingsWindow | None = None


def open_settings(root: tk.Tk, config: Config, on_change: Callable[[], None]) -> None:
    """설정창을 연다. **이미 열려 있으면 새로 만들지 않고 앞으로 끌어온다.**

    tkinter 창 조작은 메인 스레드 몫이다. 트레이(pystray 스레드)에서 부를 때는
    부르는 쪽이 Overlay.schedule로 감싼다 — overlay.py의 after(0, ...)와 같은 방식이다.
    """
    global _current
    if _current is not None and not _current._closed:
        _current.focus()
        return

    def closed() -> None:
        global _current
        _current = None
        on_change()

    _current = SettingsWindow(root, config, closed)


def sync_open(config: Config) -> None:
    """밖에서 overlay_visible·overlay_detailed가 바뀌면 부른다. 안 열려 있으면 무시.

    config는 SettingsWindow가 이미 들고 있으므로 인자로 안 받아도 되지만, 받는
    쪽에서 어떤 값이 바뀌었는지 명시하는 편이 부르는 자리를 읽기 쉽다.
    """
    if _current is not None:
        _current.sync()
