"""레지스트리 항목 목록에서 우리 것을 고르는 판정.

실제 레지스트리 접근은 얇은 껍데기(read_items·write_promoted)로 분리했고,
틀리기 쉬운 것은 51개 항목 중 무엇이 우리 것이냐다 — 실측으로 확인한 세 가지
함정이 여기 들어간다 (스펙 2.8절).
"""

from claude_usage_overlay import tray_promote as tp
from claude_usage_overlay.tray_promote import NotifyItem, pick_items

# 스펙 2.8절의 실측. ExecutablePath는 절대 경로가 아니다 — 시스템 폴더 아래
# 실행 파일은 KNOWNFOLDERID GUID 접두사로 저장된다.
POWERTOYS = NotifyItem(
    key="a1",
    tooltip="",
    exe_path=r"{6D809377-6AF0-444B-8957-A3773F02200E}\PowerToys\PowerToys.exe",
    promoted=True,
)
EXPLORER = NotifyItem(
    key="a2",
    tooltip="",
    exe_path=r"{F38BF404-1D43-42F2-9305-67DE0B28FC23}\explorer.exe",
    promoted=False,
)
CLAUDE_DESKTOP = NotifyItem(
    key="a3", tooltip="", exe_path=r"C:\Users\me\AppData\Local\Claude\Claude.exe",
    promoted=True,
)
OURS_PYTHONW = NotifyItem(
    key="b1",
    tooltip="Claude 사용량\n불러오는 중",
    exe_path=r"C:\Python312\pythonw.exe",
    promoted=False,
)
OURS_EXE = NotifyItem(
    key="b2",
    tooltip="Claude 사용량\n5시간 창  62%  ·  2시간 10분 후 리셋",
    exe_path=r"C:\Users\me\IdeaProjects\CLAUDE_HUD\dist\ClaudeUsageOverlay.exe",
    promoted=False,
)
OTHER_PYTHONW = NotifyItem(
    key="c1", tooltip="다른 파이썬 프로그램", exe_path=r"C:\Python312\pythonw.exe",
    promoted=True,
)

ALL = [POWERTOYS, EXPLORER, CLAUDE_DESKTOP, OURS_PYTHONW, OURS_EXE, OTHER_PYTHONW]


def test_the_tooltip_is_the_primary_condition():
    """ExecutablePath는 절대 경로가 아닐 수 있고, 어긋나면 기능이 아무 표시 없이
    죽는다. 툴팁으로 고르고 경로는 후보를 가리는 데만 쓴다."""
    picked = pick_items(ALL, "ClaudeUsageOverlay.exe")
    assert [i.key for i in picked] == ["b2"]


def test_a_colliding_python_path_is_not_enough():
    """같은 pythonw.exe로 도는 다른 프로그램이 잡히면 남의 아이콘을 꺼낸다."""
    picked = pick_items(ALL, "pythonw.exe")
    assert [i.key for i in picked] == ["b1"]


def test_the_claude_desktop_app_does_not_collide():
    """데스크톱 앱 항목은 툴팁이 비어 있어 접두사에 걸리지 않는다 (실측)."""
    assert CLAUDE_DESKTOP not in pick_items(ALL, "Claude.exe")


def test_a_guid_prefixed_path_is_matched_by_its_leaf_name():
    """GUID를 SHGetKnownFolderPath로 풀지 않는다. 아이콘 고정은 실패해도 조용히
    넘어가는 기능이라 그만한 정확도가 필요하지 않고, 파일 이름 비교만으로
    GUID 접두사가 자연히 흡수된다."""
    ours = NotifyItem(
        key="d1",
        tooltip="Claude 사용량\n불러오는 중",
        exe_path=r"{6D809377-6AF0-444B-8957-A3773F02200E}\Claude\ClaudeUsageOverlay.exe",
        promoted=False,
    )
    assert pick_items([ours], "ClaudeUsageOverlay.exe") == [ours]


def test_every_matching_item_is_returned():
    """같은 실행 파일에 항목이 여럿 생긴다 (실측: vgtray 4개, explorer 5개).
    소스로 돌리다 exe로 옮기면 우리 것도 여러 개가 된다."""
    twins = [
        NotifyItem("e1", "Claude 사용량\n불러오는 중", r"C:\x\app.exe", False),
        NotifyItem("e2", "Claude 사용량\n5시간 창  10%", r"C:\x\app.exe", True),
    ]
    assert [i.key for i in pick_items(twins, "app.exe")] == ["e1", "e2"]


def test_the_path_only_narrows_it_never_excludes_everything():
    """경로가 하나도 안 맞으면 툴팁으로 걸린 것을 **전부** 돌려준다.
    exe를 C:\\Program Files\\로 옮기면 sys.executable과의 비교가 어긋나는데,
    그때 빈 목록을 돌려주면 기능이 아무 표시 없이 죽는다 (스펙 2.8절)."""
    picked = pick_items([OURS_PYTHONW, OURS_EXE], "전혀다른이름.exe")
    assert [i.key for i in picked] == ["b1", "b2"]


def test_nothing_ours_means_an_empty_list():
    assert pick_items([POWERTOYS, EXPLORER, OTHER_PYTHONW], "pythonw.exe") == []


def test_promote_when_ready_waits_for_the_item_to_appear(monkeypatch):
    """항목은 아이콘이 한 번 뜬 뒤에야 탐색기가 만든다. 기동 직후에는 없다."""
    calls = []
    tries = []

    def fake_promote(value=True, name=None):
        tries.append(value)
        return len(tries) >= 3      # 세 번째에 나타난다

    monkeypatch.setattr(tp, "promote", fake_promote)
    assert tp.promote_when_ready(attempts=5, delay=0.5, sleep=calls.append) is True
    assert len(tries) == 3
    assert calls == [0.5, 0.5], "실패한 두 번 뒤에만 기다린다"


def test_promote_when_ready_gives_up_quietly(monkeypatch):
    """끝내 못 찾으면 조용히 포기한다. 예외를 던지면 기동이 멈춘다."""
    monkeypatch.setattr(tp, "promote", lambda value=True, name=None: False)
    assert tp.promote_when_ready(attempts=3, delay=0, sleep=lambda _s: None) is False


def test_exe_name_is_just_the_leaf():
    assert "\\" not in tp.exe_name() and "/" not in tp.exe_name()
    assert tp.exe_name().lower().endswith(".exe")
