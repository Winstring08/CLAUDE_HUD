"""캔버스 체크박스.

ttk.Checkbutton은 윈도우 기본 테마에서 배경·전경색이 먹지 않는다. 어두운
설정창에 얹으면 밝은 사각형이 남는다. 링과 트레이 아이콘을 이미 PIL로 그리고
있으므로 이 코드베이스에 낯선 방식은 아니다.

**체크 표시는 글꼴 글리프(`✓`)가 아니라 끝이 둥근 두꺼운 선 둘로 긋는다.**
글리프를 쓰면 글꼴마다 모양이 달라지고 획이 가늘다. capstyle="round"·
joinstyle="round"로 끝과 꺾임을 둥글게 만든다.

상자 자체는 PIL로 그린다 — 캔버스에는 둥근 사각형이 없고, create_polygon의
smooth는 스플라인이라 반경을 못 정한다 (widget_paint 머리말).
"""

import tkinter as tk
from typing import Callable

from PIL import ImageTk

from . import theme
from .widget_paint import rounded_box

BOX = 16          # 상자 한 변 (기준 픽셀)
RADIUS = 4
LABEL_GAP = 8     # 상자와 글자 사이
CHECK_WIDTH = 2
PAD_Y = 5         # 위아래 여백. 클릭 판정 높이가 이만큼 넉넉해진다


def check_points(x0: float, y0: float, size: float) -> list[tuple[float, float]]:
    """체크 표시의 꺾은선. (x0, y0)은 상자 왼쪽 위, size는 한 변.

    비율로 두는 이유는 배율마다 상자 크기가 달라지기 때문이다. 세 점은 눈으로
    고른 값이고, 왼쪽 획이 짧고 오른쪽이 긴 보통 체크 모양이다.
    """
    return [
        (x0 + size * 0.26, y0 + size * 0.52),
        (x0 + size * 0.44, y0 + size * 0.72),
        (x0 + size * 0.76, y0 + size * 0.30),
    ]


class Checkbox:
    """한 줄짜리 캔버스. 상자와 글자를 함께 담고 줄 전체가 클릭 판정이다.

    글자만 클릭 가능하게 두면 16px 상자를 정확히 노려야 하고, 줄 전체를 판정으로
    두면 실수로 눌리는 일이 늘지만 설정창의 값들은 다시 고르면 그만이다.
    """

    def __init__(
        self,
        parent: tk.Misc,
        text: str,
        checked: bool,
        on_toggle: Callable[[bool], None],
        scale: float,
        font: tuple,
        indent: int = 0,
        width: int | None = None,
    ) -> None:
        self._on_toggle = on_toggle
        self._checked = checked
        self._enabled = True
        self._text = text
        self._font = font

        self._box = round(BOX * scale)
        self._radius = max(2, round(RADIUS * scale))
        self._gap = round(LABEL_GAP * scale)
        self._check_width = max(2, round(CHECK_WIDTH * scale))
        self._indent = round(indent * scale)
        self._pad_y = round(PAD_Y * scale)

        height = self._box + self._pad_y * 2
        self._canvas = tk.Canvas(
            parent,
            width=width or 1,
            height=height,
            bg=theme.BG,
            highlightthickness=0,
            cursor="hand2",
        )
        self._canvas.bind("<Button-1>", self._click)

        # PhotoImage는 참조가 끊기면 화면에서 사라진다. 두 상태를 미리 만들어 든다.
        self._images = {
            (True, True): self._image(fill=theme.GREEN),
            (False, True): self._image(outline=theme.TEXT_DIM),
            (True, False): self._image(fill=theme.GREY),
            (False, False): self._image(outline=theme.GREY),
        }
        self._draw()

    # --- 공개 인터페이스 -------------------------------------------------

    def widget(self) -> tk.Canvas:
        return self._canvas

    def checked(self) -> bool:
        return self._checked

    def set_checked(self, checked: bool) -> None:
        """밖에서 값이 바뀌었을 때 화면만 맞춘다. on_toggle을 부르지 않는다 —
        부르면 설정창 동기화(스펙 4.4절)가 무한히 되울린다."""
        if checked == self._checked:
            return
        self._checked = checked
        self._draw()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._canvas.configure(cursor="hand2" if enabled else "")
        self._draw()

    # --- 내부 ------------------------------------------------------------

    def _image(self, fill=None, outline=None) -> ImageTk.PhotoImage:
        return ImageTk.PhotoImage(
            rounded_box(self._box, self._box, self._radius, fill=fill, outline=outline)
        )

    def _click(self, _event) -> None:
        if not self._enabled:
            return
        self._checked = not self._checked
        self._draw()
        self._on_toggle(self._checked)

    def _draw(self) -> None:
        c = self._canvas
        c.delete("all")
        x = self._indent
        c.create_image(
            x, self._pad_y, image=self._images[(self._checked, self._enabled)], anchor="nw"
        )
        if self._checked:
            # 체크 색은 채움 위에 얹히므로 어두워야 한다. 흰 체크를 GREEN 위에
            # 얹으면 대비가 3:1 아래로 떨어진다 (theme.py 주석과 같은 이유).
            c.create_line(
                *[p for point in check_points(x, self._pad_y, self._box) for p in point],
                fill=theme.TEXT_DARK if self._enabled else theme.BG,
                width=self._check_width,
                capstyle="round",
                joinstyle="round",
            )
        c.create_text(
            x + self._box + self._gap,
            self._pad_y + self._box / 2,
            text=self._text,
            anchor="w",
            fill=theme.TEXT_LIGHT if self._enabled else theme.TEXT_DIM,
            font=self._font,
        )
