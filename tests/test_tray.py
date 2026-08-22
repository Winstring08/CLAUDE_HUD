import ctypes
from ctypes import wintypes
from datetime import datetime, timedelta, timezone
from pathlib import Path

from claude_usage_overlay.icon_render import render_icon
from claude_usage_overlay.models import HudState, Status, UsageSnapshot
from claude_usage_overlay.tray import TOOLTIP_LIMIT, _load_icon_at, _tooltip, icon_key

NOW = datetime(2026, 8, 10, 3, 25, tzinfo=timezone.utc)


def state(status=Status.OK, pct=23.0, seven=15.0):
    return HudState(status, UsageSnapshot(pct, NOW + timedelta(hours=2), seven, NOW), "")


def test_icon_key_ignores_sub_percent_drift():
    """23.0%와 23.4%는 같은 그림이다. 다시 그릴 이유가 없다."""
    assert icon_key(state(pct=23.0)) == icon_key(state(pct=23.4))


def test_icon_key_changes_when_the_drawn_digit_changes():
    assert icon_key(state(pct=23.0)) != icon_key(state(pct=24.0))


def test_icon_key_changes_with_status():
    """흐림 여부가 바뀌면 같은 숫자라도 다시 그려야 한다."""
    assert icon_key(state(Status.OK)) != icon_key(state(Status.STALE))


def test_icon_key_handles_a_missing_snapshot():
    assert icon_key(HudState(Status.RELOGIN, None, "재로그인 필요")) == (Status.RELOGIN, None)


def test_tooltip_has_both_windows():
    text = _tooltip(state())
    assert "5시간 창" in text and "23%" in text
    assert "7일 창" in text and "15%" in text


def test_tooltip_omits_seven_day_when_missing():
    assert "7일 창" not in _tooltip(state(seven=None))


def test_tooltip_without_a_snapshot_shows_the_detail():
    """RELOGIN·SCHEMA_ERROR·첫 조회 전이 모두 여기로 온다."""
    text = _tooltip(HudState(Status.RELOGIN, None, "재로그인 필요 — claude auth login"))
    assert "claude auth login" in text


class _ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", wintypes.BOOL),
        ("xHotspot", wintypes.DWORD),
        ("yHotspot", wintypes.DWORD),
        ("hbmMask", ctypes.c_void_p),
        ("hbmColor", ctypes.c_void_p),
    ]


class _BITMAP(ctypes.Structure):
    _fields_ = [
        ("bmType", ctypes.c_long),
        ("bmWidth", ctypes.c_long),
        ("bmHeight", ctypes.c_long),
        ("bmWidthBytes", ctypes.c_long),
        ("bmPlanes", wintypes.WORD),
        ("bmBitsPixel", wintypes.WORD),
        ("bmBits", ctypes.c_void_p),
    ]


def _hicon_size(handle: int) -> tuple[int, int]:
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    user32.GetIconInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(_ICONINFO)]
    gdi32.GetObjectW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]

    info = _ICONINFO()
    assert user32.GetIconInfo(ctypes.c_void_p(handle), ctypes.byref(info))
    bitmap = _BITMAP()
    gdi32.GetObjectW(
        ctypes.c_void_p(info.hbmColor), ctypes.sizeof(bitmap), ctypes.byref(bitmap)
    )
    return (bitmap.bmWidth, bitmap.bmHeight)


def test_icon_is_loaded_without_being_scaled():
    """pystray 기본 경로는 LR_DEFAULTSIZE로 읽어 **32px** HICON을 만든다(실측).

    트레이가 그리는 크기는 16px이므로, 16px 그림이 32px로 늘어난 뒤 다시
    16px로 줄어든다. 그 왕복에서 숫자 획이 뭉개져 흐리게 보였다.
    크기를 명시해 읽으면 확대도 축소도 없다.
    """
    image = render_icon(state(), size=16)
    handle = _load_icon_at(image, 16)
    try:
        assert _hicon_size(handle) == (16, 16)
    finally:
        ctypes.windll.user32.DestroyIcon(ctypes.c_void_p(handle))


def test_icon_follows_a_larger_system_metric():
    """배율 150% PC의 트레이 아이콘은 24px이다. 그 크기로도 확대 없이 실려야 한다."""
    handle = _load_icon_at(render_icon(state(), size=24), 24)
    try:
        assert _hicon_size(handle) == (24, 24)
    finally:
        ctypes.windll.user32.DestroyIcon(ctypes.c_void_p(handle))


def test_tooltip_never_exceeds_the_win32_buffer():
    """szTip은 128 wchar 고정이다. 넘기면 pystray가 ValueError를 던지고,
    그게 메인 스레드의 pump() 안에서 터져 갱신 루프가 통째로 멈춘다."""
    long_detail = "재로그인 필요 — " + "가" * 300
    for state in (
        HudState(Status.RELOGIN, None, long_detail),
        HudState(Status.STALE, UsageSnapshot(23.0, NOW, 15.0, NOW), long_detail),
    ):
        assert len(_tooltip(state)) <= TOOLTIP_LIMIT


def test_the_tooltip_starts_with_the_prefix_tray_promote_looks_for():
    """tray_promote는 InitialTooltip이 이 접두사로 시작하는 항목을 우리 것으로
    고른다. 여기 첫 줄을 고치면 아이콘 고정이 아무 표시 없이 죽는다."""
    from claude_usage_overlay.tray_promote import TOOLTIP_PREFIX

    for s in (
        state(),
        state(Status.STALE),
        HudState(Status.RELOGIN, None, "재로그인 필요 — claude auth login"),
        HudState(Status.STALE, None, "불러오는 중"),
    ):
        assert _tooltip(s).startswith(TOOLTIP_PREFIX), _tooltip(s)


def test_the_menu_has_no_config_file_item():
    """설정창이 대신하므로 "설정 파일 열기"가 사라졌다. 남아 있으면 사용자가
    파일을 열어 고치고, 설정창이 닫힐 때 전체 쓰기로 그 편집을 덮는다."""
    import claude_usage_overlay.tray as tray_mod

    source = Path(tray_mod.__file__).read_text(encoding="utf-8")
    assert "설정 파일 열기" not in source
    assert "notepad" not in source
    assert "Pretendard 글꼴 설치" not in source


def test_the_menu_starts_with_a_disabled_version_item():
    """버그 제보를 받을 때 판 번호를 물어볼 유일한 수단이다.

    누를 수 있으면 안 된다 — 눌러도 아무 일이 없는 항목은 고장으로 읽힌다.
    """
    import types

    import claude_usage_overlay.tray as tray_mod
    from claude_usage_overlay.version import __version__

    stub = types.SimpleNamespace(
        _overlay=types.SimpleNamespace(is_visible=lambda: True),
        _toggle_overlay=lambda *a: None,
        _refresh_now=lambda *a: None,
        _open_settings=lambda *a: None,
        _toggle_autostart=lambda *a: None,
        _quit=lambda *a: None,
    )
    first = list(tray_mod.Tray._build_menu(stub))[0]

    assert __version__ in first.text
    assert not first.enabled
