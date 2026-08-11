"""캔버스 슬라이더.

ttk.Scale은 윈도우 기본 테마에서 색이 먹지 않고, 무엇보다 **채운 부분을
그 기준의 색으로 칠할 수 없다.** 노란 기준은 노랑, 빨간 기준은 빨강으로
칠하면 무엇을 정하는 값인지 글자를 안 읽어도 보인다 (스펙 4.2절).

값↔픽셀 환산은 순수 함수로 빼서 창 없이 테스트한다. 여기가 조용히 틀리면
화면에서는 "손잡이가 끝까지 안 간다"로 보여서 원인을 찾기 어렵다.

**트랙이 나타내는 구간(lo~hi)과 고를 수 있는 값의 범위는 다른 것이다.** 앞의 것은
고정이고, 상대 슬라이더 때문에 좁아지는 것은 뒤의 것뿐이다. 한 쌍으로 묶었다가
겪은 일이 이렇다 — 빨간 90의 손잡이가 한계 55~100에서는 235px에 있다가 노란을
올려 한계가 90~100으로 좁아지자 7px로 튀었다. 값은 그대로인데 화면에서는
"건드리지도 않은 바가 멋대로 움직인다"로 보인다.
"""

import tkinter as tk
from typing import Callable

from PIL import ImageTk

from . import theme
from .widget_paint import circle, rounded_box

TRACK_HEIGHT = 6
HANDLE = 14
VALUE_GAP = 10    # 트랙과 값 글자 사이
VALUE_WIDTH = 34  # `100%`가 들어가는 폭


# --- 판정 (순수 함수) ----------------------------------------------------


def clamp(value: float, lo: int, hi: int) -> int:
    return int(max(lo, min(hi, value)))


def snap(value: float, step: int) -> int:
    """가장 가까운 눈금으로. **경계는 위로 붙인다.**

    round()를 쓰면 안 된다. 은행가 반올림이라 72.5가 70으로 가고 77.5는 80으로
    가서, 손잡이를 같은 만큼 끌었는데 결과가 갈린다.
    """
    if step <= 0:
        return int(value)
    return int((value + step / 2) // step) * step


def value_to_x(value: int, lo: int, hi: int, x0: int, x1: int) -> int:
    """값 → 손잡이 중심의 x. x0·x1은 **손잡이 중심**이 갈 수 있는 범위다.

    트랙의 픽셀 범위가 아니라 중심 범위를 받는 이유는, 부르는 쪽이 손잡이
    반지름만큼 이미 들여놨기 때문이다. 안 들이면 최솟값·최댓값에서 손잡이의
    절반이 잘린다.
    """
    if hi <= lo:
        return x0
    ratio = (clamp(value, lo, hi) - lo) / (hi - lo)
    return round(x0 + ratio * (x1 - x0))


def x_to_value(x: int, lo: int, hi: int, x0: int, x1: int, step: int) -> int:
    """손잡이 중심의 x → 값. 범위 밖은 끝값으로 붙이고 눈금으로 스냅한다."""
    if hi <= lo or x1 <= x0:
        return lo
    ratio = (x - x0) / (x1 - x0)
    return clamp(snap(lo + ratio * (hi - lo), step), lo, hi)


# --- 위젯 ----------------------------------------------------------------


class Slider:
    def __init__(
        self,
        parent: tk.Misc,
        width: int,
        lo: int,
        hi: int,
        step: int,
        value: int,
        color: str,
        on_change: Callable[[int], None],
        scale: float,
        font: tuple,
    ) -> None:
        # lo·hi는 **트랙이 나타내는 구간**이고 바뀌지 않는다. 고를 수 있는 범위는
        # _min·_max로 따로 두고 set_limits가 좁힌다 (머리말).
        self._lo, self._hi, self._step = lo, hi, step
        self._min, self._max = lo, hi
        self._value = clamp(snap(value, step), lo, hi)
        self._color = color
        self._on_change = on_change
        self._font = font

        self._handle = max(8, round(HANDLE * scale))
        self._track_h = max(3, round(TRACK_HEIGHT * scale))
        self._value_w = round(VALUE_WIDTH * scale)
        self._gap = round(VALUE_GAP * scale)

        self._h = self._handle + 2
        # 손잡이 중심이 갈 수 있는 범위. 반지름만큼 좌우를 들인다.
        r = self._handle // 2
        self._x0 = r
        self._x1 = width - self._value_w - self._gap - r

        self._canvas = tk.Canvas(
            parent, width=width, height=self._h, bg=theme.BG,
            highlightthickness=0, cursor="hand2",
        )
        for event in ("<Button-1>", "<B1-Motion>"):
            self._canvas.bind(event, self._on_mouse)

        self._handle_photo = ImageTk.PhotoImage(circle(self._handle, theme.TEXT_LIGHT))
        self._track_photos: dict[int, ImageTk.PhotoImage] = {}
        self._draw()

    # --- 공개 인터페이스 -------------------------------------------------

    def widget(self) -> tk.Canvas:
        return self._canvas

    def value(self) -> int:
        return self._value

    def set_value(self, value: int) -> None:
        self._value = clamp(snap(value, self._step), self._min, self._max)
        self._draw()

    def set_limits(self, lo: int, hi: int) -> None:
        """고를 수 있는 값의 범위를 좁힌다. **트랙은 안 건드린다.**

        노란은 빨간보다 5%p 아래에서 멈추고 반대도 같다. 서로 밀어내지 않고 그
        자리에 서려면, 상대가 움직일 때 바뀌는 것이 **내가 갈 수 있는 데까지**여야
        하고 내가 그려지는 자리여서는 안 된다 (머리말).

        지금 값이 새 범위 밖이면 안으로 당긴다 — 손으로 고친 파일에서 올 수 있다.
        """
        self._min, self._max = lo, hi
        self.set_value(self._value)

    def handle_x(self) -> int:
        """손잡이 중심의 x. 테스트가 "값은 그대로인데 손잡이가 튀었다"를 재는 자리다."""
        return value_to_x(self._value, self._lo, self._hi, self._x0, self._x1)

    def drag_to_value(self, value: int) -> None:
        """그 값 자리를 끈 것과 같게 만든다. 한계에 걸리면 거기서 선다."""
        self._pick(value_to_x(value, self._lo, self._hi, self._x0, self._x1))

    # --- 내부 ------------------------------------------------------------

    def _on_mouse(self, event) -> None:
        self._pick(event.x)

    def _pick(self, x: int) -> None:
        """트랙 좌표 → 값. **트랙 구간으로 환산하고 한계로 자른다.**

        환산까지 한계로 하면 좁아진 범위가 트랙 전체에 다시 펼쳐져, 같은 자리를
        눌러도 상대 값에 따라 다른 값이 나온다.
        """
        raw = x_to_value(x, self._lo, self._hi, self._x0, self._x1, self._step)
        value = clamp(raw, self._min, self._max)
        if value == self._value:
            return
        self._value = value
        self._draw()
        self._on_change(value)

    def _track(self, filled_w: int) -> ImageTk.PhotoImage:
        """채운 부분과 빈 부분을 한 그림으로 만든다. 값마다 캐시한다 —
        드래그 중에 1초에 수십 번 불린다."""
        photo = self._track_photos.get(filled_w)
        if photo is None:
            width = self._x1 + self._handle // 2
            radius = self._track_h // 2
            base = rounded_box(width, self._track_h, radius, fill=theme.RING_TRACK)
            if filled_w > 0:
                fill = rounded_box(filled_w, self._track_h, radius, fill=self._color)
                base.paste(fill, (0, 0))
            photo = ImageTk.PhotoImage(base)
            self._track_photos[filled_w] = photo
        return photo

    def _draw(self) -> None:
        c = self._canvas
        c.delete("all")
        cx = self.handle_x()
        mid = self._h // 2

        c.create_image(0, mid - self._track_h // 2, image=self._track(cx), anchor="nw")
        c.create_image(cx - self._handle // 2, mid - self._handle // 2,
                       image=self._handle_photo, anchor="nw")
        c.create_text(
            self._x1 + self._handle // 2 + self._gap, mid,
            text=f"{self._value}%", anchor="w",
            fill=theme.TEXT_LIGHT, font=self._font,
        )
