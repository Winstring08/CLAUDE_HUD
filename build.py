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

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--onefile",              # exe 하나로. 상주 프로그램이라 시작 지연은 한 번뿐이다
        "--windowed",             # 콘솔 창 없음
        "--name", NAME,
        "--icon", str(icon),
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
