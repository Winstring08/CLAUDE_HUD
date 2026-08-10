"""시작 프로그램 등록. HKCU만 건드린다 (관리자 권한 불필요)."""

import sys
import winreg
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "ClaudeUsageOverlay"


def package_root() -> Path:
    """패키지를 담고 있는 디렉터리. sys.path에 이게 있어야 import가 된다."""
    return Path(__file__).resolve().parent.parent


def is_frozen() -> bool:
    """PyInstaller로 묶인 exe로 실행 중인지. 그때는 sys.executable이 우리 exe다."""
    return bool(getattr(sys, "frozen", False))


def build_command() -> str:
    """콘솔 창이 뜨지 않도록 pythonw.exe로 실행하고, 패키지 경로를 함께 넘긴다.

    **exe로 묶였을 때는 이야기가 다르다.** sys.executable이 파이썬이 아니라
    우리 exe이므로 `-c "..."`를 붙이면 그 문자열이 앱의 argv로 넘어가 버린다.
    그때는 exe 경로 하나면 충분하다.

    `pythonw -m claude_usage_overlay`만으로는 안 된다. 시작 프로그램의 cwd는
    저장소가 아니라 대개 system32이고 이 패키지는 어디에도 설치되지 않으므로
    ModuleNotFoundError가 난다. pythonw에는 콘솔이 없어서 그 오류는 아무 데도
    안 남고, 사용자는 "자동 실행이 안 켜지네"만 본다. Run 값은 문자열 하나뿐이라
    작업 디렉터리를 따로 줄 수 없으니 경로를 명령 안에 박는다.

    따옴표 규칙: 바깥은 큰따옴표, 파이썬 문자열은 작은따옴표. 중첩된 큰따옴표가
    하나라도 있으면 CommandLineToArgvW가 이 값을 잘못 쪼갠다. 경로에 슬래시를
    쓰는 것도 같은 이유다 — 백슬래시가 파이썬 문자열 안에서 이스케이프로 읽힌다.
    """
    if is_frozen():
        return f'"{sys.executable}"'

    exe = sys.executable.replace("python.exe", "pythonw.exe")
    code = (
        "import sys, runpy; "
        f"sys.path.insert(0, '{package_root().as_posix()}'); "
        "runpy.run_module('claude_usage_overlay', run_name='__main__')"
    )
    return f'"{exe}" -c "{code}"'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return bool(value)
    except OSError:
        return False


def enable() -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, build_command())


def disable() -> None:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, VALUE_NAME)
    except OSError:
        pass
