"""슬라이더 기하. 창 없이 산수만 잰다.

손잡이 반지름만큼 좌우를 들여야 손잡이가 트랙 밖으로 안 나간다. 그 들여쓰기를
빼먹으면 최솟값·최댓값에서 손잡이의 절반이 잘리는데, 화면에서는 "끝까지 안 간다"로
보여서 원인을 찾기 어렵다.

**표시 범위와 선택 가능 범위는 다른 것이다.** 트랙이 나타내는 구간(50~100)은
고정이고, 상대 슬라이더 때문에 좁아지는 것은 고를 수 있는 값의 범위뿐이다.
둘을 한 쌍으로 묶으면 상대가 움직일 때마다 내 손잡이가 제자리에서 튄다 —
그 실측이 아래 test_the_handle_does_not_move_when_only_the_limits_change에 있다.
"""

import pytest

from claude_usage_overlay.config import PCT_MAX, PCT_MIN, PCT_STEP
from claude_usage_overlay.slider import clamp, snap, value_to_x, x_to_value

X0, X1 = 20, 200   # 트랙의 왼쪽·오른쪽 끝 (손잡이 중심이 갈 수 있는 범위)


def test_clamp_keeps_a_value_inside_the_range():
    assert clamp(30, 50, 100) == 50
    assert clamp(120, 50, 100) == 100
    assert clamp(70, 50, 100) == 70


def test_snap_rounds_to_the_nearest_step():
    """세밀함보다 손으로 맞추기 쉬운 쪽을 골랐다 (스펙 4.1절)."""
    assert snap(71, 5) == 70
    assert snap(73, 5) == 75
    assert snap(72.5, 5) == 75, "경계는 위로 — round()의 은행가 반올림을 쓰면 안 된다"


def test_the_ends_land_on_the_track_ends():
    assert value_to_x(PCT_MIN, PCT_MIN, PCT_MAX, X0, X1) == X0
    assert value_to_x(PCT_MAX, PCT_MIN, PCT_MAX, X0, X1) == X1


def test_the_middle_lands_in_the_middle():
    assert value_to_x(75, 50, 100, X0, X1) == (X0 + X1) // 2


@pytest.mark.parametrize("value", range(PCT_MIN, PCT_MAX + 1, PCT_STEP))
def test_value_to_pixel_and_back_is_a_round_trip(value):
    """왕복이 어긋나면 손잡이를 안 건드렸는데 값이 한 칸 움직인다."""
    x = value_to_x(value, PCT_MIN, PCT_MAX, X0, X1)
    assert x_to_value(x, PCT_MIN, PCT_MAX, X0, X1, PCT_STEP) == value


def test_dragging_past_the_ends_is_clamped():
    assert x_to_value(X0 - 500, PCT_MIN, PCT_MAX, X0, X1, PCT_STEP) == PCT_MIN
    assert x_to_value(X1 + 500, PCT_MIN, PCT_MAX, X0, X1, PCT_STEP) == PCT_MAX


def test_the_result_is_always_on_a_step():
    """5단위가 아닌 값이 나오면 설정창이 파일에 73 같은 값을 쓰고, 다시 열면
    손잡이가 눈금 사이에 선다."""
    for x in range(X0 - 20, X1 + 20):
        got = x_to_value(x, PCT_MIN, PCT_MAX, X0, X1, PCT_STEP)
        assert got % PCT_STEP == 0, (x, got)


def test_a_narrow_track_does_not_divide_by_zero():
    """창을 아주 좁게 만든 배율에서 x0 == x1이 될 수 있다."""
    assert x_to_value(50, 50, 100, 100, 100, 5) == 50
    assert value_to_x(70, 50, 100, 100, 100) == 100


def test_a_single_point_range_does_not_divide_by_zero():
    """노란 슬라이더의 상한이 빨간에 맞춰 좁아지다 한 점이 될 수 있다."""
    assert value_to_x(50, 50, 50, X0, X1) == X0
    assert x_to_value(150, 50, 50, X0, X1, 5) == 50


# --- 표시 범위와 선택 범위의 분리 (실측한 버그) -------------------------


@pytest.fixture
def pair(root):
    """설정창과 같은 배선의 슬라이더 둘. 노란 70 · 빨간 90에서 시작한다."""
    import tkinter as tk

    from claude_usage_overlay import theme
    from claude_usage_overlay.slider import Slider

    frame = tk.Frame(root)
    seen = []
    warn = Slider(frame, 300, PCT_MIN, PCT_MAX, PCT_STEP, 70, theme.YELLOW,
                  seen.append, 1.0, ("Pretendard", -13))
    danger = Slider(frame, 300, PCT_MIN, PCT_MAX, PCT_STEP, 90, theme.RED,
                    seen.append, 1.0, ("Pretendard", -13))
    yield warn, danger
    frame.destroy()


def test_the_handle_does_not_move_when_only_the_limits_change(pair):
    """**이게 "반대쪽 바가 멋대로 움직인다"의 정체다.**

    값은 그대로인데 손잡이가 튀었다 (실측: 빨간 90의 손잡이가 한계 55~100에서
    235px, 한계가 90~100으로 좁아지자 7px). 트랙이 나타내는 구간을 한계와 같이
    두면 같은 값이 다른 자리에 그려진다.
    """
    _warn, danger = pair
    before = danger.handle_x()
    danger.set_limits(90, PCT_MAX)          # 노란을 85로 올린 상황
    assert danger.value() == 90, "값은 안 바뀐다"
    assert danger.handle_x() == before, "손잡이도 제자리여야 한다"


def test_a_limit_only_stops_the_one_being_dragged(pair):
    """노란을 끝까지 올려도 빨간은 그 자리에 선다."""
    warn, danger = pair
    warn.set_limits(PCT_MIN, danger.value() - PCT_STEP)
    warn.drag_to_value(PCT_MAX)
    assert warn.value() == 85
    assert danger.value() == 90


def test_a_value_outside_the_limits_is_pulled_in(pair):
    """한계가 값을 넘어 좁아지면(손으로 고친 파일 등) 안으로 당긴다."""
    _warn, danger = pair
    danger.set_limits(95, PCT_MAX)
    assert danger.value() == 95


def test_the_track_spans_the_whole_domain_at_both_ends(pair):
    """양 끝이 트랙의 양 끝에 서야 두 슬라이더가 같은 자로 읽힌다."""
    warn, _danger = pair
    warn.drag_to_value(PCT_MIN)
    left = warn.handle_x()
    warn.set_limits(PCT_MIN, PCT_MAX)
    warn.drag_to_value(PCT_MAX)
    assert warn.handle_x() > left
    assert warn.value() == PCT_MAX
