"""체크 표시의 기하. 창 없이 좌표만 잰다."""

from claude_usage_overlay.checkbox import check_points


def test_the_check_is_three_points_not_a_glyph():
    """글리프(`✓`)를 쓰면 글꼴마다 모양이 달라지고 획이 가늘다.
    끝이 둥근 두꺼운 선 둘로 긋는다 — 그러려면 꺾이는 점이 하나 필요하다."""
    assert len(check_points(0, 0, 16)) == 3


def test_the_check_stays_inside_the_box():
    """상자를 넘으면 체크가 잘리거나 옆 글자를 덮는다."""
    for size in (12, 16, 20, 24):
        for x, y in check_points(0, 0, size):
            assert 0 <= x <= size, (size, x)
            assert 0 <= y <= size, (size, y)


def test_the_left_stroke_is_shorter_than_the_right():
    """보통 체크 모양이다. 두 획이 같은 길이면 V자로 보인다."""
    (ax, ay), (bx, by), (cx, cy) = check_points(0, 0, 16)
    left = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
    right = ((cx - bx) ** 2 + (cy - by) ** 2) ** 0.5
    assert left < right


def test_the_middle_point_is_the_lowest():
    """꺾이는 점이 가장 아래여야 체크로 보인다."""
    points = check_points(0, 0, 16)
    assert points[1][1] == max(y for _x, y in points)


def test_the_points_move_with_the_box():
    """상자 위치를 더하기만 한다. 배율마다 상자가 다른 자리에 놓인다."""
    base = check_points(0, 0, 16)
    moved = check_points(10, 20, 16)
    assert [(x + 10, y + 20) for x, y in base] == moved


def test_the_shape_scales_with_the_box():
    """비율로 두는 이유는 배율마다 상자 크기가 달라지기 때문이다."""
    small = check_points(0, 0, 16)
    big = check_points(0, 0, 32)
    assert [(x * 2, y * 2) for x, y in small] == big
