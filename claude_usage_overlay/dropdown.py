"""캔버스 드롭다운.

ttk.Combobox는 윈도우 기본 테마에서 색이 먹지 않고, 펼친 목록은 아예 네이티브
창이라 손댈 수 없다.

**펼친 목록의 바깥 테두리를 단추의 바깥 테두리와 맞춘다.** 폭을 따로 적지 않고
좌우를 테두리 두께만큼 물려서, 항목 글자가 길어져도 어긋나지 않는다 (스펙 4.2절).

조회 주기를 드롭다운으로 만든 이유는 자유 입력에 하한이 필요하기 때문이다.
2분 아래는 호출 한도에 걸리고(config.MIN_POLL_SECONDS), 숫자를 직접 받으면
"왜 60이 안 되지"를 설명할 자리가 없다.
"""

import tkinter as tk
from typing import Callable

from PIL import ImageTk

from . import theme
from .config import MIN_POLL_SECONDS
from .widget_paint import rounded_box

# 첫 항목이 하한이다. config.MIN_POLL_SECONDS와 같아야 한다 — 어긋나면 목록에
# 고를 수 없는 값이 생기거나, 고르면 load_config가 조용히 올려버린다.
POLL_CHOICES = ((MIN_POLL_SECONDS, "2분"), (300, "5분"), (600, "10분"), (1800, "30분"))

BORDER = 1
PAD_X = 10
ROW_H = 26
RADIUS = 5
ARROW = 8    # ▾ 삼각형의 밑변


# --- 판정 (순수 함수) ----------------------------------------------------


def nearest(value: int, choices=POLL_CHOICES) -> int:
    """목록에서 가장 가까운 값.

    **같은 거리면 긴 쪽으로 붙인다.** 짧은 쪽을 고르면 측정되지 않은 호출 한도에
    더 가까워진다 — 하한 120초 자체가 측정값이 아니라는 것이
    config.MIN_POLL_SECONDS의 주석에 적혀 있다.
    """
    return min((v for v, _label in choices), key=lambda v: (abs(v - value), -v))


def label_for(value: int, choices=POLL_CHOICES) -> str:
    picked = nearest(value, choices)
    return next(label for v, label in choices if v == picked)


# --- 위젯 ----------------------------------------------------------------


class Dropdown:
    def __init__(
        self,
        parent: tk.Misc,
        choices,
        value: int,
        on_change: Callable[[int], None],
        scale: float,
        font: tuple,
        width: int,
    ) -> None:
        self._choices = tuple(choices)
        self._value = nearest(value, self._choices)
        self._on_change = on_change
        self._font = font
        self._open = False

        self._border = max(1, round(BORDER * scale))
        self._pad = round(PAD_X * scale)
        self._row = round(ROW_H * scale)
        self._radius = max(2, round(RADIUS * scale))
        self._arrow = round(ARROW * scale)
        self._w = width

        # 닫혔을 때는 단추 한 줄, 펼치면 그 아래로 항목이 늘어난다. 캔버스 높이를
        # 미리 최대로 잡아두면 그 아래 위젯이 밀려나므로 그때그때 바꾼다.
        self._canvas = tk.Canvas(
            parent, width=self._w, height=self._row, bg=theme.BG,
            highlightthickness=0, cursor="hand2",
        )
        self._canvas.bind("<Button-1>", self._click)

        self._button_photo = ImageTk.PhotoImage(
            rounded_box(self._w, self._row, self._radius,
                        outline=theme.TEXT_DIM, width=self._border)
        )
        self._panel_photo: ImageTk.PhotoImage | None = None
        self._draw()

    # --- 공개 인터페이스 -------------------------------------------------

    def widget(self) -> tk.Canvas:
        return self._canvas

    def value(self) -> int:
        return self._value

    def close(self) -> None:
        if self._open:
            self._open = False
            self._draw()

    # --- 내부 ------------------------------------------------------------

    def _panel_height(self) -> int:
        return self._row * len(self._choices)

    def _panel(self) -> ImageTk.PhotoImage:
        if self._panel_photo is None:
            self._panel_photo = ImageTk.PhotoImage(
                rounded_box(self._w, self._panel_height(), self._radius,
                            fill=theme.RING_TRACK, outline=theme.TEXT_DIM,
                            width=self._border)
            )
        return self._panel_photo

    def _click(self, event) -> None:
        if not self._open:
            self._open = True
            self._draw()
            return
        # 펼친 상태다. 단추 줄을 다시 누르면 접고, 항목 줄이면 고른다.
        index = (event.y - self._row) // self._row
        self._open = False
        if 0 <= index < len(self._choices):
            value = self._choices[index][0]
            if value != self._value:
                self._value = value
                self._on_change(value)
        self._draw()

    def _draw(self) -> None:
        c = self._canvas
        c.delete("all")
        height = self._row + (self._panel_height() if self._open else 0)
        c.configure(height=height)

        c.create_image(0, 0, image=self._button_photo, anchor="nw")
        c.create_text(
            self._pad, self._row // 2, text=label_for(self._value, self._choices),
            anchor="w", fill=theme.TEXT_LIGHT, font=self._font,
        )
        # ▾. 글리프를 쓰지 않는다 — 글꼴마다 크기와 위치가 달라 단추 안에서 뜬다.
        ax = self._w - self._pad
        ay = self._row // 2
        half = self._arrow // 2
        c.create_polygon(
            ax - self._arrow, ay - half, ax, ay - half, ax - half, ay + half,
            fill=theme.TEXT_DIM,
        )

        if not self._open:
            return

        # **바깥 테두리를 단추와 맞춘다.** 좌우를 테두리 두께만큼 물려서 항목
        # 글자가 길어져도 어긋나지 않는다.
        c.create_image(0, self._row - self._border, image=self._panel(), anchor="nw")
        for index, (value, label) in enumerate(self._choices):
            y = self._row + index * self._row + self._row // 2 - self._border
            c.create_text(
                self._pad, y, text=label, anchor="w",
                fill=theme.GREEN if value == self._value else theme.TEXT_LIGHT,
                font=self._font,
            )
