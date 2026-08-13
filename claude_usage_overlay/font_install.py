"""번들 Pretendard를 이 프로세스에 올린다.

이 프로그램의 문구는 한국어인데 Segoe UI에는 한글 글리프가 없다. 그대로 두면
숫자·영문과 한글이 서로 다른 글꼴로 그려진다. Pretendard는 둘을 한 글꼴로 덮지만
윈도우 기본 글꼴이 아니다.

**그래서 exe에 함께 묶는다.** 예전에는 트레이 메뉴로 47MB를 받아 계정 글꼴
폴더에 설치했는데, 번들이면 첫 실행부터 Pretendard다 — 기다림 0초, 네트워크 0,
실패 경로 0이다. 계정 글꼴 폴더에도 레지스트리에도 쓰지 않는다.

**GDI는 글꼴 파일을 잠그지 않는다(실측).** AddFontResourceW로 올린 채 파일을
지워도, 폴더를 통째로 지워도 성공한다. 그래서 단일 파일 exe가 종료할 때 임시
폴더를 지우는 동작이 그대로 성공하고, 종료 시 RemoveFontResourceW를 부를 필요도
찌꺼기 걱정도 없다.
"""

import ctypes
import sys
from pathlib import Path

from .winmetrics import fonts_dir

# static TTF 둘만 넣는다.
#
# variable(PretendardVariable.ttf)은 쓰지 않는다. 패밀리 이름이 "Pretendard
# Variable"로 따로 잡히는 데다 GDI가 굵기 축을 다루지 못해, bold를 요청하면
# 진짜 Bold 대신 합성된 가짜 굵기가 나온다. static Bold를 같이 올리면 그럴 일이 없다.
BUNDLE_FILES = ("Pretendard-Regular.ttf", "Pretendard-Bold.ttf")

# Tk 패밀리 이름 → TTF 파일. 잉크 상자를 재려면 파일이 필요하다 (text_center 머리말).
#
# 표로 두는 이유는 우리가 화면에 쓰는 글꼴이 둘뿐이기 때문이다 — 번들 Pretendard와,
# 번들 로드가 실패했을 때의 폴백 Segoe UI. 일반적인 패밀리→파일 해석은 레지스트리를
# 훑어야 하고 이름이 로케일에 따라 달라져 깨지기 쉽다. 표에 없는 이름이 오면
# None이고, 그때는 부르는 쪽이 잉크 정렬을 포기한다.
SEGOE_FILES = {True: "segoeuib.ttf", False: "segoeui.ttf"}


def bundle_dir() -> Path:
    """번들 글꼴이 있는 폴더.

    소스로 돌릴 때는 패키지 안의 fonts/, 단일 파일 exe로 돌릴 때는 부트로더가
    자기 자신을 풀어놓은 sys._MEIPASS 아래다. 후자를 안 보면 exe에서 글꼴을
    못 찾아 화면이 조용히 Segoe UI로 떨어진다.
    """
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "claude_usage_overlay" / "fonts"
    return Path(__file__).resolve().parent / "fonts"


def font_file_for(family: str, bold: bool = True) -> Path | None:
    """Tk 패밀리 이름 → TTF 파일 경로. 모르는 이름이면 None."""
    name = family.lower()
    if name.startswith("pretendard"):
        path = bundle_dir() / ("Pretendard-Bold.ttf" if bold else "Pretendard-Regular.ttf")
        return path if path.exists() else None
    if name == "segoe ui":
        path = fonts_dir() / SEGOE_FILES[bold]
        return path if path.exists() else None
    return None


def activate(fonts_dir: Path | None = None) -> int:
    """번들 글꼴을 **이 프로세스에서 쓸 수 있게** 올린다. 올린 개수 반환.

    AddFontResourceW로 올린 글꼴은 올린 프로세스가 살아 있는 동안만 시스템 글꼴
    목록에 남는다. 계정에 설치하는 것이 아니므로 매 기동마다 불러야 한다.

    **Tk()를 만들기 전에 불러야 한다.** Tk는 시작할 때 글꼴 목록을 읽는다.

    실패해도 조용히 넘어간다. 그때는 pick_font_family가 Segoe UI로 떨어뜨린다.
    """
    directory = fonts_dir or bundle_dir()
    loaded = 0
    for name in BUNDLE_FILES:
        path = directory / name
        if not path.exists():
            continue
        try:
            if ctypes.windll.gdi32.AddFontResourceW(ctypes.c_wchar_p(str(path))):
                loaded += 1
        except (AttributeError, OSError):
            pass
    return loaded
