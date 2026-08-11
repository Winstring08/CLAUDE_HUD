"""오버레이 우클릭 메뉴. 캔버스로 직접 그린다.

**tk.Menu를 쓰지 않는다.** 윈도우에서는 밝은 3D 테두리와 시스템 글꼴로 그려져
설정창과 따로 논다 (실측: 캡처해서 확인 — bg·fg를 줘도 바깥 테두리가 밝게 남고
글자는 Pretendard가 아닌 시스템 글꼴이다). ttk 체크박스·슬라이더·드롭다운을
캔버스로 갈아치운 것과 같은 이유이고, 판도 같은 것을 쓴다 — 드롭다운 펼친 목록과
똑같이 RING_TRACK 채움에 TEXT_DIM 테두리다.

**전역 grab을 잡지 않는다.** tk_popup은 마우스를 통째로 붙잡는데, 그 상태에서
예외가 나면 마우스가 잠긴 채 남는다. 대신 포커스를 받아 두고 포커스를 잃으면
닫는다 — 다른 창을 누르든 오버레이를 누르든 그때 닫힌다.
"""

import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass
from typing import Callable

from PIL import ImageTk

from . import theme
from .widget_paint import rounded_box
from .winmetrics import work_area

ROW_H = 26
SEP_H = 9
PAD_X = 14
RADIUS = 6
BORDER = 1
FONT_PX = 13

# 강조 띠를 판 가장자리에서 이만큼 들이고 모서리를 깎는다. 사각형으로 꽉 채우면
# 첫 줄·마지막 줄에서 판의 둥근 모서리를 덮어 각져 보인다.
HOVER_INSET = 3
HOVER_RADIUS = 4


@dataclass(frozen=True)
class Row:
    """메뉴 한 줄이 차지하는 세로 구간. index는 items의 자리, 구분선이면 None."""

    index: int | None
    y0: int
    height: int


# --- 판정 (순수 함수) ----------------------------------------------------


def layout(items, row_h: int = ROW_H, sep_h: int = SEP_H) -> list[Row]:
    """항목 목록 → 각 줄의 세로 구간.

    구분선은 항목보다 얇다. 같은 높이로 두면 메뉴가 쓸데없이 길어진다.
    """
    rows: list[Row] = []
    y = 0
    for index, item in enumerate(items):
        height = sep_h if item is None else row_h
        rows.append(Row(None if item is None else index, y, height))
        y += height
    return rows


def hit_row(y: int, rows: list[Row]) -> int | None:
    """누른 세로 좌표 → items의 자리. 구분선이나 바깥이면 None.

    구분선에서 None을 돌려주는 것이 중요하다 — 거기서 메뉴가 닫히면 누른 사람은
    뭔가 실행됐다고 여긴다.
    """
    for row in rows:
        if row.y0 <= y < row.y0 + row.height:
            return row.index
    return None


def panel_height(rows: list[Row]) -> int:
    return sum(row.height for row in rows)


def panel_width(text_widths, pad_x: int = PAD_X, scale: float = 1.0) -> int:
    """가장 긴 문구에서 역산한다. 상수로 박으면 문구가 길어질 때 조용히 잘린다."""
    return max(text_widths, default=0) + round(pad_x * scale) * 2


def fit_position(
    x: int, y: int, w: int, h: int, area: tuple[int, int, int, int]
) -> tuple[int, int]:
    """메뉴의 왼쪽 위 좌표. 마우스 자리에서 오른쪽 아래로 편다.

    **모자라면 뒤집는다.** 오버레이는 화면 오른쪽 아래에 사니까 안 뒤집으면
    메뉴가 늘 화면 밖이다. 뒤집어도 안 들어가면(메뉴가 작업 영역보다 클 때)
    안쪽으로 민다 — 음수 좌표를 만들면 안 된다.
    """
    left, top, right, bottom = area
    nx = x if x + w <= right else x - w
    ny = y if y + h <= bottom else y - h
    return (max(left, min(nx, right - w)), max(top, min(ny, bottom - h)))


# --- 창 ------------------------------------------------------------------


class _Popup:
    def __init__(
        self,
        parent: tk.Misc,
        items: list[tuple[str, Callable[[], None]] | None],
        scale: float,
        family: str,
    ) -> None:
        self._items = list(items)
        self._rows = layout(
            self._items, round(ROW_H * scale), round(SEP_H * scale)
        )
        self._font = (family, -round(FONT_PX * scale))
        self._pad = round(PAD_X * scale)
        self._closed = False

        self._win = tk.Toplevel(parent)
        self._win.overrideredirect(True)
        self._win.attributes("-topmost", True)
        self._win.configure(bg=theme.BG)

        measure = tkfont.Font(root=self._win, family=family, size=self._font[1])
        self._w = panel_width(
            [measure.measure(item[0]) for item in self._items if item],
            PAD_X,
            scale,
        )
        self._h = panel_height(self._rows)

        self._canvas = tk.Canvas(
            self._win, width=self._w, height=self._h, bg=theme.BG,
            highlightthickness=0, cursor="hand2",
        )
        self._canvas.pack()
        self._panel = ImageTk.PhotoImage(
            rounded_box(self._w, self._h, max(2, round(RADIUS * scale)),
                        fill=theme.RING_TRACK, outline=theme.TEXT_DIM,
                        width=max(1, round(BORDER * scale)))
        )
        self._hover: int | None = None
        # 강조 띠. 판과 같은 바탕색 위에 그려야 모서리가 자연스럽게 이어진다.
        self._hover_inset = max(1, round(HOVER_INSET * scale))
        self._hover_photos: dict[int, ImageTk.PhotoImage] = {}
        self._draw()

        self._canvas.bind("<Motion>", self._on_motion)
        self._canvas.bind("<Leave>", self._on_leave)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self._win.bind("<Escape>", lambda _e: self.close())
        self._win.bind("<FocusOut>", lambda _e: self.close())

    def show(self, x_root: int, y_root: int) -> None:
        x, y = fit_position(x_root, y_root, self._w, self._h, work_area())
        self._win.geometry(f"{self._w}x{self._h}+{x}+{y}")
        self._win.lift()
        self._win.focus_force()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._win.destroy()

    # --- 내부 ------------------------------------------------------------

    def _on_motion(self, event) -> None:
        index = hit_row(event.y, self._rows)
        if index != self._hover:
            self._hover = index
            self._draw()

    def _on_leave(self, _event) -> None:
        if self._hover is not None:
            self._hover = None
            self._draw()

    def _on_release(self, event) -> None:
        index = hit_row(event.y, self._rows)
        if index is None:
            return
        command = self._items[index][1]
        # **먼저 닫고 실행한다.** 항목이 창을 여는 경우, 메뉴가 남아 있으면
        # 그 창 위에 얹힌 채로 뜬다 (메뉴가 topmost다).
        self.close()
        if command is not None:
            command()

    def _hover_band(self, height: int) -> ImageTk.PhotoImage:
        photo = self._hover_photos.get(height)
        if photo is None:
            photo = ImageTk.PhotoImage(
                rounded_box(
                    self._w - self._hover_inset * 2, height, HOVER_RADIUS,
                    fill=theme.GREY, bg=theme.RING_TRACK,
                )
            )
            self._hover_photos[height] = photo
        return photo

    def _draw(self) -> None:
        c = self._canvas
        c.delete("all")
        c.create_image(0, 0, image=self._panel, anchor="nw")
        for row in self._rows:
            if row.index is None:
                y = row.y0 + row.height // 2
                c.create_line(
                    self._pad, y, self._w - self._pad, y, fill=theme.GREY,
                )
                continue
            if row.index == self._hover:
                c.create_image(
                    self._hover_inset, row.y0, image=self._hover_band(row.height),
                    anchor="nw",
                )
            c.create_text(
                self._pad, row.y0 + row.height // 2,
                text=self._items[row.index][0], anchor="w",
                fill=theme.TEXT_LIGHT, font=self._font,
            )


# 열려 있는 메뉴는 하나뿐이다. 두 번째 우클릭은 앞의 것을 닫고 새로 연다.
_current: _Popup | None = None


def show(
    parent: tk.Misc,
    items: list[tuple[str, Callable[[], None]] | None],
    x_root: int,
    y_root: int,
    scale: float,
    family: str,
) -> None:
    """메뉴를 연다. items의 원소는 (문구, 실행할 것)이고 None은 구분선이다."""
    global _current
    if _current is not None:
        _current.close()
    _current = _Popup(parent, items, scale, family)
    _current.show(x_root, y_root)


def is_open() -> bool:
    """메뉴가 떠 있는지.

    오버레이가 이걸 보고 항상 위 재주장을 쉰다. 안 그러면 1초 안에 오버레이가
    **자기 메뉴 위로** 올라가 메뉴를 덮는다 (실측) — 메뉴는 커서 자리에 뜨고
    커서는 방금 오버레이를 누른 자리이므로 반드시 겹친다.
    """
    return _current is not None and not _current._closed
