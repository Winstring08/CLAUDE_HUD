"""잉크 상자를 재서 상자 중앙에 놓는 좌표 계산.

**tkinter는 문자열의 잉크 상자를 알려주지 않는다.** Font.metrics()에는
ascent·descent·linespace만 있고, Canvas.bbox()가 돌려주는 것은 잉크가 아니라
**레이아웃 상자**다. 그래서 잉크는 PIL로 같은 글꼴 파일을 열어 재고, Tk 좌표로는
baseline을 경유해서 옮긴다.

**ascender선을 경유하면 안 된다.** Tk와 PIL이 ascent를 다르게 센다 (실측:
Pretendard Bold 18px에서 Tk 17 · PIL 18, Segoe UI Bold 15px에서 Tk 16 · PIL 17).
잉크 위치를 ascender선 기준으로 넘기면 이 1px이 그대로 어긋난다. baseline 기준
값은 글꼴 파일 자체의 성질이라 양쪽이 같다.

**icon_render._centered_text를 베끼면 안 된다.** 잉크 상자를 매번 재는 것은
맞지만 좌표를 round()로 맞추고 있고, 파이썬의 round()는 은행가 반올림이라
절반은 아래로 간다 — round(1.5)=2(아래), round(2.5)=2(위), round(0.5)=0(위).
값의 홀짝에 따라 방향이 갈리므로 "남는 반 픽셀은 위로"가 지켜지지 않는다.
여기서는 //(floor)로 명시한다.

이 공식은 스펙 2.6절이 화면을 캡처해 픽셀을 센 결과를 그대로 재현한다 —
Pretendard 18px `100`, 링 안쪽 top=13·높이 40에서 잉크 26~38, 위 13 · 아래 14.
"""

from dataclasses import dataclass
from pathlib import Path

from PIL import ImageFont


@dataclass(frozen=True)
class Ink:
    """실제로 칠해지는 상자.

    left·right는 펜 시작점 기준, top·bottom은 **baseline 기준**이다.
    baseline 위가 음수이므로 숫자는 top이 음수이고 bottom이 0이다.
    """

    left: int
    right: int
    top: int
    bottom: int


def measure_ink(font_path: Path | None, px: int, text: str) -> Ink | None:
    """글꼴 파일을 열어 잉크 상자를 잰다. 못 열면 None.

    None을 돌려주는 것은 실패가 아니라 정상 경로다. 부르는 쪽은 그때 잉크 정렬을
    포기하고 레이아웃 상자 중앙에 놓으면 된다 — 1px 어긋날 뿐 화면은 정상이다.
    """
    if font_path is None:
        return None
    try:
        font = ImageFont.truetype(str(font_path), px)
    except (OSError, ValueError):
        return None
    ascent, _descent = font.getmetrics()
    try:
        left, top, right, bottom = font.getbbox(text)
    except (OSError, ValueError):
        return None
    # PIL 기본 anchor는 "la"(left-ascender)라 y=0이 ascender선이다.
    # baseline은 그로부터 ascent 아래에 있으므로 빼서 baseline 기준으로 옮긴다.
    return Ink(int(left), int(right), int(top) - ascent, int(bottom) - ascent)


def center_start(box_size: int, ink_size: int) -> int:
    """상자 안에서 잉크가 시작할 위치. 남는 반 픽셀은 **앞쪽(위·왼쪽)으로.**

    //는 floor다. round()로 하면 은행가 반올림이라 방향이 갈린다 (머리말).
    """
    return (box_size - ink_size) // 2


def nw_xy(box: tuple[int, int, int, int], ink: Ink, ascent: int) -> tuple[int, int]:
    """create_text(anchor="nw")에 넘길 좌표.

    box는 (x0, y0, x1, y1)이고 폭은 x1 - x0다. ascent는 **Tk의** 값이다 —
    anchor="nw"로 그리면 레이아웃 상자 위쪽이 y에 놓이고 baseline은 y + ascent다.
    """
    x0, y0, x1, y1 = box
    x = x0 + center_start(x1 - x0, ink.right - ink.left) - ink.left
    y = y0 + center_start(y1 - y0, ink.bottom - ink.top) - ascent - ink.top
    return x, y
