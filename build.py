"""실행 파일을 만든다.

    python build.py

결과: dist\\ClaudeUsageOverlay.exe (단일 파일, 콘솔 없음)

필요한 것:
    pip install pyinstaller
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAME = "ClaudeUsageOverlay"
ICON = ROOT / "build" / "app.ico"

# 앱 아이콘 크기들. 윈도우가 상황에 따라 골라 쓴다 —
# 작업 표시줄은 32px, 탐색기 큰 아이콘은 256px.
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)

VERSION_FILE = ROOT / "build" / "version_info.txt"

# exe 파일 속성에 박히는 값들. LICENSE의 저작권자와 같은 이름이어야 한다.
COMPANY = "권승현"
COPYRIGHT = f"Copyright (c) 2026 {COMPANY}. MIT License."


def version_tuple(text: str) -> tuple[int, int, int, int]:
    """"0.1.0" → (0, 1, 0, 0). VS_VERSION_INFO는 네 칸을 요구한다."""
    parts = tuple(int(p) for p in text.split("."))
    return parts + (0,) * (4 - len(parts))


def make_version_file() -> Path:
    """탐색기 → 속성 → 자세히에 보일 값을 만든다.

    서명이 없는 exe는 메타데이터까지 비어 있으면 백신 오탐을 더 받는다. 그리고
    사용자가 프로그램을 띄우지 않고도 판 번호를 확인할 경로가 하나 생긴다.

    한글이 들어가도 된다 — PyInstaller가 이 파일을 UTF-8로 읽고 다시 파싱해
    같은 문자열을 돌려주는 것을 확인했다(스펙 9장 2번).
    """
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )

    from claude_usage_overlay.version import __version__

    parts = version_tuple(__version__)
    info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=parts, prodvers=parts),
        kids=[
            StringFileInfo(
                [
                    # 040904B0 = 미국 영어 + UTF-16. 문구가 한국어라도 이 코드페이지를
                    # 쓴다 — 값 자체는 UTF-16으로 들어가므로 한글이 그대로 실린다.
                    StringTable(
                        "040904B0",
                        [
                            StringStruct("CompanyName", COMPANY),
                            StringStruct("FileDescription", "Claude 사용량 오버레이"),
                            StringStruct("FileVersion", __version__),
                            StringStruct("InternalName", NAME),
                            StringStruct("LegalCopyright", COPYRIGHT),
                            StringStruct("OriginalFilename", f"{NAME}.exe"),
                            StringStruct("ProductName", "Claude Usage Overlay"),
                            StringStruct("ProductVersion", __version__),
                        ],
                    )
                ]
            ),
            VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
        ],
    )

    VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    VERSION_FILE.write_text(str(info), encoding="utf-8")
    return VERSION_FILE


def make_icon() -> Path:
    """앱 아이콘을 만든다. 트레이 아이콘과 같은 링 게이지 모양이다.

    숫자는 넣지 않는다 — 앱 아이콘에 특정 사용률이 박혀 있으면 뜻이 이상하다.
    """
    from PIL import Image, ImageDraw

    from claude_usage_overlay import theme
    from claude_usage_overlay.ring_render import _rgb

    size = 256
    scale = size // 16
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        [(0, 0), (size - 1, size - 1)], radius=size // 5, fill=_rgb(theme.BG)
    )

    pad, width = size * 0.22, max(4, 3 * scale)
    box = [pad, pad, size - pad, size - pad]
    draw.arc(box, 0, 360, fill=_rgb(theme.RING_TRACK), width=width)
    draw.arc(box, -90, -90 + 360 * 0.62, fill=_rgb(theme.FILL_GREEN), width=width)

    ICON.parent.mkdir(parents=True, exist_ok=True)
    img.save(ICON, sizes=[(s, s) for s in ICON_SIZES])
    return ICON


def build() -> int:
    icon = make_icon()
    print(f"아이콘: {icon}")

    version_file = make_version_file()
    print(f"버전 파일: {version_file}")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--onefile",              # exe 하나로. 상주 프로그램이라 시작 지연은 한 번뿐이다
        "--windowed",             # 콘솔 창 없음
        "--name", NAME,
        "--icon", str(icon),
        # 빌드하는 기계에 UPX가 깔려 있으면 PyInstaller가 묻지 않고 쓴다. 그러면
        # 개발 PC와 CI가 서로 다른 exe를 낸다. 게다가 UPX로 압축된 바이너리는
        # 서명 없는 exe에 특히 나쁜 백신 오탐을 더 받는다. 축을 없앤다.
        "--noupx",
        # 탐색기 속성 창에 제품 이름·버전·저작권을 보인다.
        "--version-file", str(version_file),
        # pystray는 백엔드를 실행 시점에 고르므로 정적 분석에 안 잡힌다.
        "--hidden-import", "pystray._win32",
        "--hidden-import", "PIL._tkinter_finder",
        # 글꼴은 정적 분석에 안 잡힌다. 우리가 경로로 여는 데이터 파일이다.
        # 구분자는 os.pathsep — 윈도우에서는 ';'다.
        "--add-data",
        f"{ROOT / 'claude_usage_overlay' / 'fonts'}{os.pathsep}claude_usage_overlay/fonts",
        str(ROOT / "app.py"),
    ]
    print(" ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode == 0:
        exe = ROOT / "dist" / f"{NAME}.exe"
        print(f"\n완성: {exe}  ({exe.stat().st_size / 1024 / 1024:.1f} MB)")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(build())
