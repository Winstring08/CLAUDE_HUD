"""PC마다 달라지는 화면 지표를 한 곳에 가둔다.

윈도우 설치 드라이브, 화면 배율, 모니터 구성은 여기서만 다룬다.
나머지 모듈은 그 차이를 모른다.
"""

import ctypes
import os
from ctypes import wintypes
from pathlib import Path

SM_CXSMICON = 49
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

DEFAULT_ICON_SIZE = 16
MIN_VISIBLE_W = 40
MIN_VISIBLE_H = 20

DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2   # 큰 반경. 3(ROUNDSMALL)은 눈에 띄지 않을 만큼 작다


def enable_dpi_awareness() -> None:
    """Windows에게 "우리가 배율을 직접 처리한다"고 알린다. Tk()보다 먼저 부른다.

    tkinter는 기본적으로 DPI 비인식이라 Windows가 창을 통째로 비트맵 확대한다.
    그 상태에서 우리가 치수에 dpi_scale()을 곱하면 확대가 두 번 걸려 창이
    배율의 제곱만큼 커진다 — 150%에서 2.25배다. 이걸 부르면 Windows가
    확대를 멈추고 우리 곱셈만 남는다.

    실패해도 조용히 넘어간다. 창이 흐릿하거나 커질 뿐이고, HUD가 안 뜨는 것보다 낫다.
    """
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)   # Windows 8.1+
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()        # 그 이전
    except (AttributeError, OSError):
        pass


def round_window_corners(hwnd: int) -> bool:
    """창 모서리를 둥글게 만든다. 성공하면 True.

    무테두리 창(overrideredirect)은 기본적으로 직각이다. DWM에 맡기면
    부드러운 곡선에 그림자까지 붙는다 — 이 창은 항상 위에 떠 있으므로
    경계가 배경과 구분되는 편이 낫다.

    gdi32의 SetWindowRgn으로 직접 잘라내는 방법도 있고 반경을 마음대로
    고를 수 있지만 쓰지 않는다. 안티앨리어싱이 없어 모서리가 계단으로
    보인다(실측: r=8·12 모두 픽셀 계단이 그대로 드러난다). DWM 쪽은
    반경을 못 고르는 대신 곡선이 매끈하다.

    Windows 10 이하에서는 이 속성이 없어 실패한다. 그때는 예전처럼 각진
    창이 될 뿐이므로 조용히 넘어간다 — 모서리 때문에 HUD가 안 뜨면 안 된다.
    """
    try:
        value = ctypes.c_int(DWMWCP_ROUND)
        rc = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            ctypes.c_uint(DWMWA_WINDOW_CORNER_PREFERENCE),
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
        return rc == 0
    except (AttributeError, OSError, ValueError, TypeError):
        return False


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
