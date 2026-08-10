"""tkinter 오버레이 창.

1초마다 다시 그리지만 네트워크는 부르지 않는다. 카운트다운은
resets_at에서 로컬로 계산한다. 화면은 매초 살아 움직이고 API는 5분에 한 번만.

모든 픽셀 치수는 기준값 × DPI 배율이다. 배율 150% PC에서도 같은 크기로 보인다.
글꼴만 규칙이 다르다 — fonts_for()의 주석을 보라.
"""

import tkinter as tk
from datetime import datetime, timezone

from . import theme
from .config import Config, save_config
from .formatting import format_age, format_countdown
from .models import HudState, Status
from .winmetrics import dpi_scale, is_position_visible, virtual_screen_rect

# 폭 240은 눈대중이 아니라 역산이다. 가장 긴 문구인 RELOGIN 뒷줄
# "Claude Code를 한 번 실행하세요"가 11px Segoe UI에서 163px이고,
# BASE_TEXT_X(66) + 163 + BASE_RIGHT_MARGIN(10) = 239다.
# create_text에는 width 옵션이 없어 넘치면 경고 없이 잘린다.
# tests/test_overlay_layout.py가 이 여유를 지킨다.
BASE_WIDTH, BASE_HEIGHT = 240, 62
BASE_RING_BOX = (12, 12, 54, 54)   # x0, y0, x1, y1
BASE_RING_WIDTH = 5
BASE_TEXT_X = 66
BASE_LINE1_Y, BASE_LINE2_Y = 24, 40
BASE_RIGHT_MARGIN = 10
MARGIN = 24
ALPHA = 0.82

# 글꼴 크기는 픽셀이다. 음수로 넘긴다 (Tk 규약: 음수 = 픽셀, 양수 = 포인트).
BASE_FONT_PCT_PX = 13
BASE_FONT_LINE1_PX = 12
BASE_FONT_LINE2_PX = 11

# 값이 낡은 상태. 아이콘과 같은 기준을 쓴다.
DIM_STATUSES = frozenset({Status.STALE, Status.RATE_LIMITED})


def fonts_for(scale: float) -> dict[str, tuple]:
    """글꼴 크기를 **픽셀**로 만든다. Tk에서 음수 = 픽셀, 양수 = 포인트다.

    포인트로 주면 안 된다. enable_dpi_awareness()를 켜는 순간 Tk의
    `tk scaling`이 실제 DPI를 따라가고, 포인트→픽셀 환산이 이미 배율을
    반영한다. 거기에 dpi_scale()을 또 곱하면 확대가 두 번 걸린다 —
    144 DPI에서 10pt는 28px인데 round(10 × 1.5) = 15pt를 주면 41px이 되어
    기대값 26px의 약 1.6배가 된다. 캔버스 치수는 픽셀이라 곱셈이 맞으므로
    창은 제 크기인데 글자만 넘쳐 잘린다.

    픽셀 크기는 tk scaling에 흔들리지 않는다(실측: scaling 1.333과 2.0에서
    -13px 모두 linespace 17px). 그래서 여기서만 배율을 곱하면 되고,
    캔버스 치수와 정확히 같은 비율로 커진다.
    """
    return {
        "pct": ("Segoe UI", -round(BASE_FONT_PCT_PX * scale), "bold"),
        "line1": ("Segoe UI", -round(BASE_FONT_LINE1_PX * scale)),
        "line2": ("Segoe UI", -round(BASE_FONT_LINE2_PX * scale)),
    }


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
        fonts = fonts_for(s)
        self._font_pct = fonts["pct"]
        self._font_line1 = fonts["line1"]
        self._font_line2 = fonts["line2"]

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
        self._visible = config.overlay_visible
        if not self._visible:
            self._win.withdraw()
        self._tick()

    # --- 공개 인터페이스 -------------------------------------------------
    #
    # show/hide/is_visible은 **트레이 메뉴에서 불린다 — 즉 pystray 스레드다.**
    # tkinter 창 조작은 메인 스레드 몫이므로 여기서 직접 하지 않고 after()로
    # 넘긴다. 표시 여부도 Tk에 묻지 않고 우리가 들고 있는다.

    def update(self, state: HudState) -> None:
        self._state = state

    def show(self) -> None:
        self._set_visible(True)

    def hide(self) -> None:
        self._set_visible(False)

    def is_visible(self) -> bool:
        """Tk에 묻지 않는다. 트레이 메뉴 문구를 그릴 때마다 불리는 함수라
        pystray 스레드에서 Tk를 건드리게 된다."""
        return self._visible

    def _set_visible(self, visible: bool) -> None:
        """after()는 콜백을 tkinter 이벤트 큐에 넣을 뿐이고,
        실제 withdraw/deiconify는 메인 스레드의 mainloop가 실행한다."""
        self._visible = visible
        self._config.overlay_visible = visible
        save_config(self._config)
        self._win.after(0, self._win.deiconify if visible else self._win.withdraw)

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
            # 문구는 credentials가 정한다. "제목 — 할 일" 형태를 두 줄로 나눈다.
            head, _, tail = state.detail.partition(" — ")
            self._draw_ring(0, theme.GREY)
            self._draw_text(head or "재로그인 필요", theme.RED, tail, theme.TEXT_DIM)
            return

        if state.snapshot is None:
            # 첫 조회 전(STALE)과 SCHEMA_ERROR가 모두 여기로 온다. 문구는
            # 만든 쪽이 정하므로 오버레이는 기호를 고를 필요가 없다 —
            # 트레이 아이콘만 "…"와 "?"를 구분한다.
            self._draw_ring(0, theme.GREY)
            self._draw_text(state.detail or "불러오는 중", theme.TEXT_DIM, "", theme.TEXT_DIM)
            return

        snap = state.snapshot
        pct = snap.five_hour_pct
        color = theme.color_for(pct, self._config.warn_pct, self._config.danger_pct)
        dim = state.status in DIM_STATUSES

        self._draw_ring(pct, "#3a3f4b" if dim else color)
        c.create_text(
            (self._ring[0] + self._ring[2]) / 2,
            (self._ring[1] + self._ring[3]) / 2,
            text=f"{int(round(pct))}%",
            fill="#6d7280" if dim else theme.TEXT_LIGHT,
            font=self._font_pct,
        )

        # resets_at이 None이면 "—"가 온다. 링과 숫자는 그대로 그린다.
        line1 = format_countdown(snap.resets_at, now)
        if state.status is Status.STALE:
            line2, line2_color = state.detail, theme.YELLOW
        elif state.status is Status.RATE_LIMITED:
            line2, line2_color = "호출 한도 — 잠시 후 재시도", theme.YELLOW
        else:
            line2, line2_color = format_age(snap.fetched_at, now), theme.TEXT_DIM

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
