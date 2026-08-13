"""우클릭 메뉴의 배치와 판정.

대부분은 창 없이 산수만 잰다. 마지막 몫만 실제 창을 만드는데, 거기서 재는 것이
"눌렀을 때 무엇이 실행되고 언제 닫히는가"라 창 없이는 확인할 수 없기 때문이다.
"""

import pytest

from claude_usage_overlay import menu_popup as mp
from claude_usage_overlay.menu_popup import fit_position, hit_row, layout

ITEMS = [("설정…", None), ("자세히 보기", None), None, ("오버레이 숨기기", None)]


def test_a_separator_gets_its_own_slim_band():
    """구분선을 항목과 같은 높이로 두면 메뉴가 쓸데없이 길어진다."""
    rows = layout(ITEMS, row_h=26, sep_h=9)
    assert [r.height for r in rows] == [26, 26, 9, 26]


def test_the_rows_stack_without_gaps_or_overlap():
    """빈틈이 있으면 그 자리를 눌렀을 때 아무 항목도 안 걸린다."""
    rows = layout(ITEMS, row_h=26, sep_h=9)
    assert rows[0].y0 == 0
    for before, after in zip(rows, rows[1:]):
        assert before.y0 + before.height == after.y0


def test_a_press_on_a_command_hits_it():
    rows = layout(ITEMS, row_h=26, sep_h=9)
    assert hit_row(0, rows) == 0
    assert hit_row(25, rows) == 0
    assert hit_row(26, rows) == 1


def test_a_press_on_a_separator_hits_nothing():
    """구분선을 눌러 메뉴가 닫히면 누른 사람은 뭔가 실행됐다고 여긴다."""
    rows = layout(ITEMS, row_h=26, sep_h=9)
    sep = rows[2]
    assert hit_row(sep.y0, rows) is None
    assert hit_row(sep.y0 + sep.height - 1, rows) is None


def test_a_press_past_the_end_hits_nothing():
    rows = layout(ITEMS, row_h=26, sep_h=9)
    assert hit_row(-1, rows) is None
    assert hit_row(sum(r.height for r in rows), rows) is None


def test_the_menu_opens_down_and_right_of_the_pointer():
    """마우스가 왼쪽 위 모서리에 오는 것이 데스크톱 메뉴의 관례다."""
    assert fit_position(300, 200, 160, 100, (0, 0, 1920, 1040)) == (300, 200)


def test_a_menu_near_the_right_edge_flips_to_the_left():
    """오버레이는 화면 오른쪽 아래에 산다. 안 뒤집으면 메뉴가 늘 화면 밖이다."""
    x, _y = fit_position(1900, 200, 160, 100, (0, 0, 1920, 1040))
    assert x == 1900 - 160


def test_a_menu_near_the_bottom_flips_up():
    _x, y = fit_position(300, 1030, 160, 100, (0, 0, 1920, 1040))
    assert y == 1030 - 100


def test_a_menu_bigger_than_the_screen_still_starts_inside():
    """뒤집어도 안 들어가면 작업 영역 안으로 민다. 음수 좌표를 만들면 안 된다."""
    x, y = fit_position(10, 10, 400, 300, (0, 0, 200, 200))
    assert (x, y) == (0, 0)


def test_the_taskbar_edge_is_respected():
    """작업 영역의 top이 0이 아닌 배치(표시줄이 위)도 있다."""
    _x, y = fit_position(300, 60, 160, 100, (0, 48, 1920, 1080))
    assert y >= 48


def test_the_panel_is_wide_enough_for_the_longest_label():
    """폭을 상수로 박으면 문구가 길어질 때 조용히 잘린다 — 설정창과 같은 이유로
    가장 긴 문구에서 역산한다."""
    widths = {"설정…": 40, "자세히 보기": 90, "오버레이 숨기기": 120}
    assert mp.panel_width(widths.values(), pad_x=14, scale=1.0) == 120 + 14 * 2


# --- 실제 창에서의 동작 -------------------------------------------------


@pytest.fixture
def opened(root):
    """열린 메뉴 하나와, 눌린 항목이 쌓이는 목록."""
    picked = []
    items = [
        ("설정…", lambda: picked.append("설정")),
        ("자세히 보기", lambda: picked.append("자세히")),
        None,
        ("오버레이 숨기기", lambda: picked.append("숨기기")),
    ]
    mp.show(root, items, 200, 200, 1.0, "Pretendard")
    popup = mp._current
    root.update()
    yield popup, picked
    popup.close()


def _release(popup, y):
    popup._canvas.event_generate("<ButtonRelease-1>", x=20, y=y)
    popup._win.update()


def test_pressing_a_row_runs_it_once_and_closes(opened):
    popup, picked = opened
    _release(popup, popup._rows[1].y0 + 2)
    assert picked == ["자세히"]
    assert popup._closed is True


def test_pressing_the_separator_does_nothing_and_stays_open(opened):
    """구분선에서 닫히면 누른 사람은 뭔가 실행됐다고 여긴다."""
    popup, picked = opened
    _release(popup, popup._rows[2].y0 + 1)
    assert picked == []
    assert popup._closed is False


def test_escape_closes_without_running_anything(opened):
    popup, picked = opened
    popup._win.event_generate("<Escape>")
    popup._win.update()
    assert picked == []
    assert popup._closed is True


def test_losing_focus_closes_it(opened):
    """전역 grab을 안 잡으므로 이게 유일한 바깥 클릭 처리다. 이게 안 되면
    메뉴가 화면에 남아 아무 데도 안 닫힌다."""
    popup, _picked = opened
    popup._win.event_generate("<FocusOut>")
    popup._win.update()
    assert popup._closed is True


def test_opening_a_second_menu_closes_the_first(root):
    """두 번 우클릭하면 앞의 것이 남아 겹친다."""
    mp.show(root, [("가", lambda: None)], 100, 100, 1.0, "Pretendard")
    first = mp._current
    mp.show(root, [("나", lambda: None)], 300, 300, 1.0, "Pretendard")
    second = mp._current
    root.update()
    try:
        assert first is not second
        assert first._closed is True
        assert second._closed is False
    finally:
        second.close()
