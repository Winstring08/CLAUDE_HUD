"""작업 표시줄에 트레이 아이콘을 고정한다. Windows 11 전용.

Windows 11은 아이콘 표시 여부를 HKCU\\Control Panel\\NotifyIconSettings\\<해시>의
IsPromoted DWORD에 담는다. **값을 쓰면 탐색기가 바로 따라온다** — 켜면 아이콘이
작업 표시줄로 나오고, 끄면 ∧ 안으로 들어간다. 로그오프도 탐색기 재시작도 필요 없다.

**예전 주석은 "즉시 반영되지 않는다 · 다음 로그온부터"라고 적어두었고 그것은
틀렸다.** 그 판정은 Claude Code(MSIX 패키지 앱)의 Bash에서 띄운 인스턴스로 잰
것이었는데, 패키지 컨테이너 안에서는 HKCU 쓰기가 패키지 전용 하이브
(...\\Packages\\Claude_*\\SystemAppData\\Helium\\User.dat)로 재지정되어 **탐색기가
그 값을 볼 수 없다.** 컨테이너 밖(사용자가 직접 띄운 인스턴스, 재부팅 뒤 자동
실행)에서는 예외 없이 즉시 반영된다.

여기서 얻을 교훈은 이 기능에 국한되지 않는다 — **이 프로그램의 동작을 검증할
때는 컨테이너 밖에서 띄운 인스턴스로 재야 한다.** %APPDATA%도 같은 이유로
재지정되므로 config.json 저장도 컨테이너 안에서는 딴 곳에 쓰인다.

**탐색기를 재시작하지 않는다.** 사용자의 열린 창을 전부 건드리는 짓이고,
그럴 이유도 없다.

**Windows 10은 하지 않는다.** Win10은 IconStreams 이진 blob에 담고 형식이
문서화돼 있지 않아 OS 버전마다 바뀔 수 있다. 전역 스위치(EnableAutoTray=0)는
있지만 모든 앱에 적용되므로 우리가 조용히 켤 값이 아니다. Win10에는 아이콘별
설정 화면이 따로 있으니 설정창의 안내가 그쪽을 가리킨다
(settings_window.PROMOTE_HINT_WIN10).

HKCU만 건드린다. 관리자 권한이 필요 없고, 우리가 만들지 않은 항목에는 쓰지 않는다.
"""

import sys
import time
import winreg
from dataclasses import dataclass
from pathlib import Path

NOTIFY_KEY = r"Control Panel\NotifyIconSettings"

# InitialTooltip에는 툴팁이 줄바꿈까지 그대로 들어 있다. 실측으로 우리 항목은
# "Claude 사용량\n불러오는 중"이었고, 51개 중 이것으로 시작하는 것은 우리뿐이다 —
# Claude 데스크톱 앱 항목은 툴팁이 비어 있어 겹치지 않는다.
#
# tray._tooltip()이 만드는 첫 줄과 같아야 한다. 그쪽을 고치면 여기도 고친다.
TOOLTIP_PREFIX = "Claude 사용량"


@dataclass(frozen=True)
class NotifyItem:
    key: str        # NotifyIconSettings 하위 키 이름 (해시)
    tooltip: str    # InitialTooltip
    exe_path: str   # ExecutablePath. **절대 경로가 아닐 수 있다** (머리말)
    promoted: bool


# --- 판정 (순수 함수) ----------------------------------------------------


def _leaf(path: str) -> str:
    return path.replace("/", "\\").rsplit("\\", 1)[-1].lower()


def pick_items(items: list[NotifyItem], exe_name: str) -> list[NotifyItem]:
    """항목 목록에서 우리 것.

    **툴팁을 주 조건으로 두고 경로는 후보를 가리는 데만 쓴다.** ExecutablePath는
    시스템 폴더 아래에서 KNOWNFOLDERID GUID 접두사로 저장되고(실측), 설치
    프로그램이 없으므로 사용자가 exe를 C:\\Program Files\\에 두는 순간
    sys.executable과의 문자열 비교가 어긋난다. 필수 조건으로 쓰면 그 순간 기능이
    아무 표시 없이 죽는다.

    경로 비교는 **파일 이름만** 본다. GUID를 SHGetKnownFolderPath로 풀 수는 있고
    실측으로 셋 다 풀렸지만, 아이콘 고정은 실패해도 조용히 넘어가는 기능이라
    그만한 정확도가 필요하지 않다. 이름 비교만으로 GUID 접두사가 자연히 흡수된다.

    **맞는 항목이 여럿이면 전부 돌려준다.** 같은 실행 파일에 항목이 여러 개
    생기는 것을 실측했다(vgtray 4개, explorer 5개). 소스로 돌리다 exe로 옮기면
    우리 것도 여러 개가 된다.
    """
    ours = [i for i in items if i.tooltip.startswith(TOOLTIP_PREFIX)]
    narrowed = [i for i in ours if _leaf(i.exe_path) == exe_name.lower()]
    return narrowed or ours


def exe_name() -> str:
    """지금 프로세스의 실행 파일 이름. 소스로 돌리면 pythonw.exe다."""
    return Path(sys.executable).name


# --- 레지스트리 (얇은 껍데기) --------------------------------------------


def is_supported() -> bool:
    """키가 있는 환경인지. Windows 10 이하에는 없다."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, NOTIFY_KEY):
            return True
    except OSError:
        return False


def _read_one(parent, name: str) -> NotifyItem | None:
    def value(key, field, default):
        try:
            got, _type = winreg.QueryValueEx(key, field)
            return got
        except OSError:
            return default

    try:
        with winreg.OpenKey(parent, name) as sub:
            return NotifyItem(
                key=name,
                tooltip=str(value(sub, "InitialTooltip", "")),
                exe_path=str(value(sub, "ExecutablePath", "")),
                promoted=bool(value(sub, "IsPromoted", 0)),
            )
    except OSError:
        return None


def read_items() -> list[NotifyItem]:
    """하위 키를 전부 읽는다. 못 읽으면 빈 목록 — 예외를 던지지 않는다."""
    items: list[NotifyItem] = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, NOTIFY_KEY) as parent:
            index = 0
            while True:
                try:
                    name = winreg.EnumKey(parent, index)
                except OSError:
                    break
                index += 1
                item = _read_one(parent, name)
                if item is not None:
                    items.append(item)
    except OSError:
        return []
    return items


def write_promoted(keys: list[str], value: bool) -> bool:
    """IsPromoted를 쓴다. 하나라도 썼으면 True."""
    if not keys:
        return False
    written = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, NOTIFY_KEY) as parent:
            for name in keys:
                try:
                    with winreg.OpenKey(parent, name, 0, winreg.KEY_SET_VALUE) as sub:
                        winreg.SetValueEx(
                            sub, "IsPromoted", 0, winreg.REG_DWORD, 1 if value else 0
                        )
                    written += 1
                except OSError:
                    continue
    except OSError:
        return False
    return written > 0


def is_promoted(name: str | None = None) -> bool:
    """우리 항목이 모두 고정돼 있는지. 항목이 없으면 False.

    쓰고 나서 이 함수로 다시 읽어 체크박스를 그린다. 안 그러면 화면이 거짓말을 한다.
    """
    ours = pick_items(read_items(), name or exe_name())
    return bool(ours) and all(i.promoted for i in ours)


def promote(value: bool = True, name: str | None = None) -> bool:
    """찾아서 쓴다. 못 찾으면 조용히 False."""
    ours = pick_items(read_items(), name or exe_name())
    return write_promoted([i.key for i in ours], value)


def promote_when_ready(
    attempts: int = 10,
    delay: float = 3.0,
    sleep=time.sleep,
    name: str | None = None,
) -> bool:
    """항목이 생길 때까지 기다렸다 쓴다. 별도 스레드에서 부른다.

    **항목은 아이콘이 한 번 뜬 뒤에야 탐색기가 만든다.** 기동 직후에는 없으므로
    한 번 보고 포기하면 첫 실행 자동 시도가 늘 실패한다. 기본값이면 최대 30초쯤
    기다리고, 끝내 못 찾으면 조용히 포기한다 — 예외를 던지면 기동이 멈춘다.
    """
    for remaining in range(attempts, 0, -1):
        if promote(True, name):
            return True
        if remaining > 1:
            sleep(delay)
    return False
