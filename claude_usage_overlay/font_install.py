"""Pretendard 글꼴을 계정 글꼴 폴더에 설치한다.

이 프로그램의 문구는 한국어인데 Segoe UI에는 한글 글리프가 없다. 그대로 두면
숫자·영문과 한글이 서로 다른 글꼴로 그려진다. Pretendard는 둘을 한 글꼴로 덮지만
윈도우 기본 글꼴이 아니라서, 쓰는 사람마다 직접 깔아야 하는 문제가 남는다.
그 한 단계를 프로그램이 대신한다.

**관리자 권한이 필요한 경로는 건드리지 않는다.** 파일은 계정 글꼴 폴더에 쓰고
등록도 HKCU에만 한다. 스펙 9.2장이 자동 실행 등록을 허용한 근거가 여기에도
그대로 적용된다 — 우리가 만든 값만 다루고, 최악의 결과는 "글꼴이 안 깔린다"이며,
되돌리기는 파일과 값을 지우는 것으로 끝난다.

네트워크·디스크·레지스트리를 건드리는 부분은 얇게 두고, 무엇을 받아 무엇을
꺼낼지 고르는 판정만 순수 함수로 빼서 테스트한다.
"""

import ctypes
import io
import json
import winreg
import zipfile
from ctypes import wintypes
from pathlib import Path
from typing import Callable

from . import http_client
from .winmetrics import user_fonts_dir

RELEASE_API = "https://api.github.com/repos/orioncactus/pretendard/releases/latest"
USER_AGENT = "claude-usage-overlay"

# 받을 것은 static TTF 둘뿐이다.
#
# variable(PretendardVariable.ttf)은 쓰지 않는다. 패밀리 이름이 "Pretendard
# Variable"로 따로 잡히는 데다 GDI가 굵기 축을 다루지 못해, bold를 요청하면
# 진짜 Bold 대신 합성된 가짜 굵기가 나온다. static Bold를 같이 깔면 그럴 일이 없다.
#
# .otf가 아니라 alternative/ 쪽 .ttf를 쓰는 이유는 GDI 렌더링이 TrueType 힌팅에서
# 더 안정적이기 때문이다.
WANTED_FILES = ("Pretendard-Regular.ttf", "Pretendard-Bold.ttf")

FONTS_REG_KEY = r"Software\Microsoft\Windows NT\CurrentVersion\Fonts"

HWND_BROADCAST = 0xFFFF
WM_FONTCHANGE = 0x001D
SMTO_ABORTIFHUNG = 0x0002


# --- 판정 (순수 함수) ----------------------------------------------------


def pick_zip_asset(assets: list[dict]) -> str:
    """릴리스 자산 목록에서 받을 zip의 URL.

    같은 릴리스에 GOV·JP·Std 변종이 함께 올라온다. 우리가 원하는 것은
    `Pretendard-1.3.9.zip`처럼 이름 바로 뒤에 하이픈이 오는 것뿐이고,
    변종들은 `PretendardGOV-`, `PretendardStd-`라서 이 접두사에 걸리지 않는다.
    """
    for asset in assets:
        name = str(asset.get("name", ""))
        if name.startswith("Pretendard-") and name.endswith(".zip"):
            return str(asset["browser_download_url"])
    raise LookupError("릴리스에서 Pretendard zip을 찾지 못했습니다")


def wanted_members(names) -> dict[str, str]:
    """zip 안의 경로 중 설치할 것만 {파일명: zip 내부 경로}로.

    zip에는 웹폰트(woff2)와 otf, variable까지 40여 개가 들어 있다. 경로 구조가
    판올림에서 바뀔 수 있으므로 디렉터리가 아니라 파일 이름으로 고른다.
    """
    found: dict[str, str] = {}
    for path in names:
        leaf = path.replace("\\", "/").rsplit("/", 1)[-1]
        if leaf in WANTED_FILES and leaf not in found:
            found[leaf] = path
    return found


def registry_value_name(file_name: str) -> str:
    """윈도우 글꼴 목록에 보일 이름. `Pretendard Regular (TrueType)` 꼴이다."""
    stem = file_name.rsplit(".", 1)[0].replace("-", " ")
    return f"{stem} (TrueType)"


def is_installed(fonts_dir: Path | None = None) -> bool:
    """설치 파일이 모두 자리에 있는지.

    Tk의 글꼴 목록으로 판정하지 않는다. 그러려면 Tk 인스턴스가 있어야 하는데
    이 함수는 트레이 메뉴가 그려질 때마다 pystray 스레드에서 불린다.
    """
    directory = fonts_dir or user_fonts_dir()
    return all((directory / name).exists() for name in WANTED_FILES)


# --- 설치 ----------------------------------------------------------------


def fetch_zip(request_fn: Callable = http_client.request) -> bytes:
    """최신 릴리스의 zip을 받아 온다. 47MB쯤 된다."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}

    res = request_fn("GET", RELEASE_API, headers, timeout=30.0)
    if res.status != 200:
        raise OSError(f"릴리스 정보를 받지 못했습니다 (HTTP {res.status})")
    url = pick_zip_asset(json.loads(res.body).get("assets", []))

    res = request_fn("GET", url, {"User-Agent": USER_AGENT}, timeout=300.0)
    if res.status != 200:
        raise OSError(f"글꼴을 내려받지 못했습니다 (HTTP {res.status})")
    return res.body


def extract_to(zip_bytes: bytes, target_dir: Path) -> list[Path]:
    """필요한 ttf만 꺼내 target_dir에 쓴다. 이미 있으면 덮어쓴다."""
    target_dir.mkdir(parents=True, exist_ok=True)
    archive = zipfile.ZipFile(io.BytesIO(zip_bytes))
    members = wanted_members(archive.namelist())
    if len(members) != len(WANTED_FILES):
        missing = set(WANTED_FILES) - set(members)
        raise LookupError(f"zip 안에 {', '.join(sorted(missing))}이(가) 없습니다")

    written = []
    for leaf, path in members.items():
        destination = target_dir / leaf
        # 임시 파일에 쓰고 바꿔치운다. 쓰는 중인 파일을 GDI가 읽으면
        # 깨진 글꼴로 등록될 수 있다.
        tmp = destination.with_suffix(".ttf.part")
        tmp.write_bytes(archive.read(path))
        tmp.replace(destination)
        written.append(destination)
    return written


def register(paths: list[Path]) -> None:
    """설치한 글꼴을 이 계정에 등록하고, 실행 중인 프로그램들에 알린다.

    HKCU에만 쓴다. 계정 글꼴은 값에 파일명이 아니라 전체 경로를 넣어야 한다.
    """
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, FONTS_REG_KEY) as key:
        for path in paths:
            winreg.SetValueEx(
                key, registry_value_name(path.name), 0, winreg.REG_SZ, str(path)
            )

    # 이 세션에서도 바로 쓸 수 있게 로드한다. 실패해도 등록 자체는 남으므로
    # 다음 로그온에는 정상으로 잡힌다.
    for path in paths:
        try:
            ctypes.windll.gdi32.AddFontResourceW(ctypes.c_wchar_p(str(path)))
        except (AttributeError, OSError):
            pass

    try:
        ctypes.windll.user32.SendMessageTimeoutW(
            wintypes.HWND(HWND_BROADCAST),
            ctypes.c_uint(WM_FONTCHANGE),
            0,
            0,
            ctypes.c_uint(SMTO_ABORTIFHUNG),
            ctypes.c_uint(1000),
            None,
        )
    except (AttributeError, OSError):
        pass


def activate(fonts_dir: Path | None = None) -> int:
    """설치돼 있는 글꼴을 **이 프로세스에서 쓸 수 있게** 올린다. 올린 개수 반환.

    기동할 때마다 부른다. 그러지 않으면 방금 설치한 글꼴이 다음 로그온 전까지
    보이지 않는다 — 이유가 둘 겹쳐 있다.

      · `AddFontResourceW`로 올린 글꼴은 **올린 프로세스가 살아 있는 동안만**
        시스템 글꼴 목록에 남는다. 설치를 끝낸 프로세스가 종료되면 빠진다.
      · 레지스트리 등록(HKCU\\...\\Fonts)은 **다음 로그온부터** 반영된다.

    그래서 "설치했는데 글꼴이 그대로"인 구간이 생긴다. 기동 시 한 번 올리면
    그 구간이 사라진다. 이미 올라와 있어도 무해하다.

    Tk()를 만들기 전에 불러야 한다. Tk는 시작할 때 글꼴 목록을 읽는다.
    """
    directory = fonts_dir or user_fonts_dir()
    loaded = 0
    for name in WANTED_FILES:
        path = directory / name
        if not path.exists():
            continue
        try:
            if ctypes.windll.gdi32.AddFontResourceW(ctypes.c_wchar_p(str(path))):
                loaded += 1
        except (AttributeError, OSError):
            pass
    return loaded


def install(
    request_fn: Callable = http_client.request, fonts_dir: Path | None = None
) -> list[Path]:
    """받아서 풀고 등록하기까지. 이미 깔려 있으면 아무것도 하지 않는다."""
    directory = fonts_dir or user_fonts_dir()
    if is_installed(directory):
        return [directory / name for name in WANTED_FILES]

    paths = extract_to(fetch_zip(request_fn), directory)
    register(paths)
    return paths
