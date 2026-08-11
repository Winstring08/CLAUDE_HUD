"""PC마다 달라지는 화면 지표를 한 곳에 가둔다.

윈도우 설치 드라이브, 화면 배율, 트레이 아이콘 크기는 여기서만 다룬다.
나머지 모듈은 그 차이를 모른다.
"""

import ctypes
import os
from ctypes import wintypes
from pathlib import Path

SM_CXSMICON = 49
SPI_GETWORKAREA = 0x0030

DEFAULT_ICON_SIZE = 16

DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2   # 큰 반경. 3(ROUNDSMALL)은 눈에 띄지 않을 만큼 작다
DWMWA_USE_IMMERSIVE_DARK_MODE = 20


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


def dark_title_bar(hwnd: int) -> bool:
    """네이티브 창의 제목 표시줄만 어둡게 만든다. 성공하면 True.

    **무테두리로 직접 그릴 필요가 없다.** 이 속성 하나로 제목 표시줄이 어두워지고
    창 이동·Alt+Tab·스냅·작업 표시줄은 전부 정상으로 남는다 (실측: rc=0, 대조군
    창과 나란히 띄워 육안 확인).

    round_window_corners와 같은 API다. 함수가 하나 늘 뿐이다.

    Windows 10 초기 판올림에는 이 속성이 없어 실패한다. 그때는 제목 표시줄만
    밝은 채로 뜬다 — 보기 나쁠 뿐 동작에는 지장이 없으므로 조용히 넘어간다.
    """
    try:
        value = ctypes.c_int(1)
        rc = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            ctypes.c_uint(DWMWA_USE_IMMERSIVE_DARK_MODE),
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
        return rc == 0
    except (AttributeError, OSError, ValueError, TypeError):
        return False


def fonts_dir() -> Path:
    """윈도우가 C: 아닌 드라이브에 설치돼 있어도 폰트를 찾는다."""
    return Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"


def user_fonts_dir() -> Path:
    """계정에만 설치된 글꼴이 있는 곳.

    글꼴을 우클릭해 "설치"를 누르면 관리자 권한 없이 여기로 들어간다.
    시스템 Fonts 폴더만 보면 그렇게 깔린 글꼴을 통째로 놓친다.
    """
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        return fonts_dir()
    return Path(base) / "Microsoft" / "Windows" / "Fonts"


def _metric(index: int) -> int:
    try:
        return int(ctypes.windll.user32.GetSystemMetrics(index))
    except (AttributeError, OSError):
        return 0


def system_icon_size() -> int:
    """배율 100%에서 16, 125%에서 20, 150%에서 24를 돌려준다."""
    size = _metric(SM_CXSMICON)
    return size if size > 0 else DEFAULT_ICON_SIZE


def work_area() -> tuple[int, int, int, int]:
    """작업 표시줄을 뺀 화면 영역 (left, top, right, bottom).

    화면 크기(`winfo_screenheight`)를 쓰면 안 된다. 그건 작업 표시줄까지
    포함한 값이라, 창을 아래쪽에 붙이면 표시줄 뒤로 들어가 버린다.
    이 값은 표시줄이 아래에 있든 위·옆에 있든, 자동 숨김이든 알아서 맞는다.

    실패하면 주 화면 전체를 돌려준다. 창이 표시줄에 조금 가릴 뿐이고,
    HUD가 안 뜨는 것보다 낫다.
    """
    rect = wintypes.RECT()
    try:
        ok = ctypes.windll.user32.SystemParametersInfoW(
            ctypes.c_uint(SPI_GETWORKAREA), 0, ctypes.byref(rect), 0
        )
        if ok:
            return (rect.left, rect.top, rect.right, rect.bottom)
    except (AttributeError, OSError):
        pass

    width = _metric(0) or 1920    # SM_CXSCREEN
    height = _metric(1) or 1080   # SM_CYSCREEN
    return (0, 0, width, height)


def dpi_scale() -> float:
    try:
        dpi = int(ctypes.windll.user32.GetDpiForSystem())
    except (AttributeError, OSError):
        dpi = 96
    return max(1.0, dpi / 96.0)
