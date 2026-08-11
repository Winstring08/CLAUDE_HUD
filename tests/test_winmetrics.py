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


def test_work_area_excludes_the_taskbar():
    """오버레이를 오른쪽 아래에 붙이는 기준이다.

    화면 크기를 쓰면 작업 표시줄 뒤로 창이 숨는다. 작업 영역은 그 표시줄을
    뺀 값이므로 화면보다 작거나(표시줄이 있으면) 같아야(자동 숨김) 한다.
    """
    import ctypes

    left, top, right, bottom = winmetrics.work_area()
    screen_w = ctypes.windll.user32.GetSystemMetrics(0)
    screen_h = ctypes.windll.user32.GetSystemMetrics(1)

    assert right > left and bottom > top
    assert right - left <= screen_w
    assert bottom - top <= screen_h


def test_dark_title_bar_succeeds_on_this_windows(root):
    """DwmSetWindowAttribute(hwnd, 20, TRUE)가 rc=0을 돌려주는지 실제로 본다.
    Windows 10 초기 판올림에는 이 속성이 없어 실패하는데, 그때는 제목 표시줄만
    밝게 뜰 뿐이라 조용히 넘어간다 (스펙 11장).

    루트는 conftest.py의 세션 픽스처다 — 여기서 tk.Tk()를 따로 만들면 그 뒤에
    오는 Tk 테스트가 통째로 죽는다 (conftest 머리말).
    """
    import tkinter as tk

    from claude_usage_overlay.winmetrics import dark_title_bar

    win = tk.Toplevel(root)
    try:
        win.update_idletasks()
        hwnd = int(win.wm_frame(), 16)
        assert dark_title_bar(hwnd) is True
    finally:
        win.destroy()


def test_keep_on_top_succeeds_on_a_real_window(root):
    """오버레이가 1초마다 부르는 함수다. 실제로 성공하는지 본다."""
    import tkinter as tk

    from claude_usage_overlay.winmetrics import keep_on_top

    win = tk.Toplevel(root)
    try:
        win.update_idletasks()
        assert keep_on_top(int(win.wm_frame(), 16)) is True
    finally:
        win.destroy()


def test_keep_on_top_does_not_steal_focus(root):
    """SWP_NOACTIVATE가 빠지면 1초마다 포커스를 빼앗아 다른 창에서 타자를
    칠 수 없게 된다. 부르기 전후로 포커스 주인이 그대로여야 한다."""
    import ctypes
    import tkinter as tk

    from claude_usage_overlay.winmetrics import keep_on_top

    other = tk.Toplevel(root)
    target = tk.Toplevel(root)
    try:
        for win in (other, target):
            win.update_idletasks()
        other.focus_force()
        other.update()
        before = ctypes.windll.user32.GetForegroundWindow()
        keep_on_top(int(target.wm_frame(), 16))
        target.update()
        assert ctypes.windll.user32.GetForegroundWindow() == before
    finally:
        target.destroy()
        other.destroy()


def test_keep_on_top_is_quiet_on_a_bogus_handle():
    """오버레이 _tick 안에서 돈다. 여기서 던지면 화면 갱신이 통째로 멈춘다."""
    from claude_usage_overlay.winmetrics import keep_on_top

    for bogus in (0, -1, 12345):
        assert keep_on_top(bogus) in (True, False)


def test_dark_title_bar_is_quiet_on_a_bogus_handle():
    """실패해도 예외를 던지지 않는다. 여기서 던지면 설정창이 아예 안 열린다."""
    from claude_usage_overlay.winmetrics import dark_title_bar

    assert dark_title_bar(0) is False


def test_round_window_corners_never_raises():
    """Overlay.__init__에서 불린다. 여기서 죽으면 HUD가 아예 안 뜬다.

    Windows 10 이하에는 이 DWM 속성이 없고, 창이 아직 배치되기 전이면
    핸들도 쓸모없는 값이다. 어느 쪽이든 각진 창이 될 뿐이어야 한다.
    """
    for bogus in (0, -1, 12345):
        assert winmetrics.round_window_corners(bogus) in (True, False)
