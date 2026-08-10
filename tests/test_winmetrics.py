from pathlib import Path

from claude_usage_overlay import winmetrics


def test_fonts_dir_follows_windir(monkeypatch):
    monkeypatch.setenv("WINDIR", r"D:\Windows")
    assert winmetrics.fonts_dir() == Path(r"D:\Windows\Fonts")


def test_fonts_dir_falls_back_when_windir_missing(monkeypatch):
    monkeypatch.delenv("WINDIR", raising=False)
    assert winmetrics.fonts_dir() == Path(r"C:\Windows\Fonts")


def test_system_icon_size_is_plausible():
    size = winmetrics.system_icon_size()
    assert isinstance(size, int)
    assert 8 <= size <= 64


def test_dpi_scale_is_at_least_one():
    assert winmetrics.dpi_scale() >= 1.0


def test_enable_dpi_awareness_is_safe_to_call():
    """이미 설정돼 있거나 API가 없어도 예외를 던지면 안 된다.

    __main__에서 가장 먼저 부르는 함수다. 여기서 죽으면 HUD가 아예 안 뜬다.
    """
    winmetrics.enable_dpi_awareness()
    winmetrics.enable_dpi_awareness()   # 두 번째 호출은 실패하지만 조용해야 한다


def test_round_window_corners_never_raises():
    """Overlay.__init__에서 불린다. 여기서 죽으면 HUD가 아예 안 뜬다.

    Windows 10 이하에는 이 DWM 속성이 없고, 창이 아직 배치되기 전이면
    핸들도 쓸모없는 값이다. 어느 쪽이든 각진 창이 될 뿐이어야 한다.
    """
    for bogus in (0, -1, 12345):
        assert winmetrics.round_window_corners(bogus) in (True, False)
