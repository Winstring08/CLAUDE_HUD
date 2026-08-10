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


def test_virtual_screen_rect_has_positive_extent():
    _x, _y, w, h = winmetrics.virtual_screen_rect()
    assert w > 0 and h > 0


RECT = (0, 0, 2560, 1440)  # x, y, width, height


def test_window_fully_inside_is_visible():
    assert winmetrics.is_position_visible(100, 100, 186, 62, RECT)


def test_window_far_off_to_the_right_is_not_visible():
    assert not winmetrics.is_position_visible(4000, 100, 186, 62, RECT)


def test_window_far_above_is_not_visible():
    assert not winmetrics.is_position_visible(100, -500, 186, 62, RECT)


def test_window_with_enough_overlap_counts_as_visible():
    # 오른쪽 끝에 60px 걸쳐 있으면 드래그로 되찾을 수 있다
    assert winmetrics.is_position_visible(2500, 100, 186, 62, RECT)


def test_window_with_a_sliver_showing_is_not_visible():
    # 20px만 걸쳐 있으면 사실상 못 찾는다
    assert not winmetrics.is_position_visible(2540, 100, 186, 62, RECT)


def test_secondary_monitor_left_of_primary_is_visible():
    # 보조 모니터가 왼쪽에 있으면 가상 화면 원점이 음수다
    rect = (-1920, 0, 4480, 1440)
    assert winmetrics.is_position_visible(-1800, 200, 186, 62, rect)
