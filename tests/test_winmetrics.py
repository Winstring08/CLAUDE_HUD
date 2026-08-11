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


def test_a_window_is_centered_in_the_work_area():
    """설정창·안내창은 자리를 안 정하면 Tk 기본값대로 화면 왼쪽 위에 뜬다."""
    from claude_usage_overlay.winmetrics import centered_position

    assert centered_position(400, 300, (0, 0, 1920, 1040)) == (760, 370)


def test_centering_uses_the_work_area_not_the_screen():
    """작업 표시줄을 뺀 영역의 한가운데다. 화면 기준으로 잡으면 표시줄 높이의
    절반만큼 아래로 처진다."""
    from claude_usage_overlay.winmetrics import centered_position

    _x, y = centered_position(400, 300, (0, 48, 1920, 1080))
    assert y == 48 + (1032 - 300) // 2


def test_a_window_taller_than_the_screen_still_starts_inside():
    """음수 좌표를 만들면 제목 표시줄이 화면 밖으로 나가 창을 못 옮긴다."""
    from claude_usage_overlay.winmetrics import centered_position

    assert centered_position(3000, 2000, (0, 0, 1920, 1040)) == (0, 0)


def test_centering_respects_a_left_offset_work_area():
    """작업 표시줄이 왼쪽에 있으면 작업 영역의 left가 0이 아니다."""
    from claude_usage_overlay.winmetrics import centered_position

    x, _y = centered_position(400, 300, (72, 0, 1920, 1080))
    assert x == 72 + (1848 - 400) // 2


def test_frame_size_is_bigger_than_the_content(root):
    """제목 표시줄과 테두리만큼 크다. 이 차이를 무시하고 가운데를 잡으면
    창이 그만큼 오른쪽 아래로 처진다."""
    import tkinter as tk

    from claude_usage_overlay.winmetrics import frame_size

    win = tk.Toplevel(root)
    try:
        win.geometry("400x300+100+100")
        win.update_idletasks()
        outer = frame_size(int(win.wm_frame(), 16))
        assert outer is not None
        assert outer[0] > 400 and outer[1] > 300
    finally:
        win.destroy()


def test_frame_size_is_quiet_on_a_bogus_handle():
    """못 재면 None이다. 그때는 부르는 쪽이 내용 크기로 가늠한다."""
    from claude_usage_overlay.winmetrics import frame_size

    assert frame_size(0) is None


def test_center_window_puts_the_frame_in_the_middle(root):
    """**보이는 창**의 중심이 작업 영역 중심과 맞아야 한다. 내용 크기로만
    가운데를 잡으면 제목 표시줄 높이의 절반만큼 아래로 처진다."""
    import tkinter as tk

    from claude_usage_overlay.winmetrics import center_window, frame_size, work_area

    win = tk.Toplevel(root)
    try:
        center_window(win, 400, 300)
        win.update_idletasks()
        left, top, right, bottom = work_area()
        fw, fh = frame_size(int(win.wm_frame(), 16))
        x, y = win.winfo_x(), win.winfo_y()
        assert abs((x + fw // 2) - (left + right) // 2) <= 1
        assert abs((y + fh // 2) - (top + bottom) // 2) <= 1
    finally:
        win.destroy()


def test_center_window_works_before_the_window_is_shown(root):
    """자리를 다 잡은 뒤에 보여줘야 왼쪽 위에 잠깐 떴다 튀지 않는다.
    숨어 있는 동안에도 프레임을 잴 수 있어야 그게 된다 (실측).

    winfo_x가 아니라 geometry 문자열로 잰다 — 배치되지 않은 창의 winfo_x는
    늘 0이라, 그걸로 보면 가운데로 옮겨진 창도 왼쪽 끝으로 읽힌다.
    """
    import tkinter as tk

    from claude_usage_overlay.winmetrics import center_window, frame_size, work_area

    win = tk.Toplevel(root)
    win.withdraw()
    try:
        center_window(win, 400, 300)
        win.update_idletasks()
        _size, x, y = win.geometry().replace("+", " +").split()
        left, top, right, bottom = work_area()
        fw, fh = frame_size(int(win.wm_frame(), 16))
        assert abs((int(x) + fw // 2) - (left + right) // 2) <= 1
        assert abs((int(y) + fh // 2) - (top + bottom) // 2) <= 1
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
