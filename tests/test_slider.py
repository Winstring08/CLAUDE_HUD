"""슬라이더 기하. 창 없이 산수만 잰다.

손잡이 반지름만큼 좌우를 들여야 손잡이가 트랙 밖으로 안 나간다. 그 들여쓰기를
빼먹으면 최솟값·최댓값에서 손잡이의 절반이 잘리는데, 화면에서는 "끝까지 안 간다"로
보여서 원인을 찾기 어렵다.
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
