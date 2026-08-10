"""링 이미지가 실제로 매끈한지, 사용률만큼 채워지는지 잰다.

창을 띄우지 않는다. 링은 순수 함수가 만드는 이미지이므로 픽셀로 확인할 수 있다.
"""

from claude_usage_overlay import theme
from claude_usage_overlay.ring_render import render_ring

SIZE = 42   # 오버레이의 기본 링 지름 (BASE_RING_BOX 54-12)
WIDTH = 5


def ring(pct, color=theme.GREEN):
    return render_ring(SIZE, pct, color, bg=theme.BG, width=WIDTH)


def _pixels(img):
    px = img.load()
    return [px[x, y] for y in range(img.height) for x in range(img.width)]


def _colors(img):
    return set(_pixels(img))


def test_size_and_mode():
    img = ring(23.0)
    assert img.size == (SIZE, SIZE)
    assert img.mode == "RGB"


def test_edges_are_antialiased():
    """이게 이 모듈의 존재 이유다.

    create_arc에는 안티앨리어싱이 없어 링 색과 배경색 딱 둘만 나온다.
    크게 그려 축소하면 경계에 중간톤이 생기고, 그 중간톤이 계단을 지운다.
    """
    img = ring(50.0)
    green, bg = _rgb(theme.GREEN), _rgb(theme.BG)
    track = _rgb(theme.RING_TRACK)

    def is_pure(px):
        return px in (green, bg, track)

    blended = [px for px in _pixels(img) if not is_pure(px)]
    # 42px 링의 곡선 경계에는 중간톤이 수십 개는 나온다
    assert len(blended) > 50, f"중간톤 픽셀이 {len(blended)}개뿐 — 계단이다"


def _rgb(color):
    color = color.lstrip("#")
    return (int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16))


def _is_green(px):
    r, g, b = px
    return g > r + 30 and g > b + 20


def test_fill_grows_with_usage():
    def greenish(pct):
        return sum(1 for px in _pixels(ring(pct)) if _is_green(px))

    assert greenish(10.0) < greenish(50.0) < greenish(95.0)


def test_zero_percent_draws_only_the_track():
    """사용량 0에서도 링의 테두리는 남아야 자리가 보인다."""
    empty = ring(0.0)
    assert sum(1 for px in _pixels(empty) if _is_green(px)) == 0
    assert _rgb(theme.RING_TRACK) in _colors(empty)


def test_full_percent_fills_all_around():
    """100%는 링을 한 바퀴 채운다. 12시 이음매 말고는 트랙이 안 보인다."""
    track = _rgb(theme.RING_TRACK)
    full_track = sum(1 for px in _pixels(ring(100.0)) if px == track)
    half_track = sum(1 for px in _pixels(ring(50.0)) if px == track)
    assert full_track < half_track / 4


def _green_by_quadrant(img):
    """(오른쪽위, 오른쪽아래, 왼쪽아래, 왼쪽위) 순 — 시계방향."""
    mid = img.width // 2
    px = img.load()
    counts = [0, 0, 0, 0]
    for y in range(img.height):
        for x in range(img.width):
            if not _is_green(px[x, y]):
                continue
            right, bottom = x >= mid, y >= mid
            counts[0 if (right and not bottom) else 1 if (right and bottom) else 2 if bottom else 3] += 1
    return counts


def test_starts_at_twelve_oclock_and_goes_clockwise():
    """25%면 12시에서 3시까지, 즉 오른쪽 위 사분면만 찬다.

    픽셀 하나를 찍는 대신 사분면별로 세는 이유는 링이 가늘어서(5px)
    좌표를 조금만 잘못 골라도 밴드를 비껴가기 때문이다.
    """
    top_right, bottom_right, bottom_left, top_left = _green_by_quadrant(ring(25.0))
    assert top_right > 20
    assert bottom_right + bottom_left + top_left < top_right / 3


def test_half_fills_the_right_side():
    """50%면 12시에서 6시까지 — 오른쪽 절반이다."""
    top_right, bottom_right, bottom_left, top_left = _green_by_quadrant(ring(50.0))
    assert top_right > 20 and bottom_right > 20
    assert bottom_left + top_left < top_right / 3


def test_custom_size_still_renders():
    """배율 150% PC에서는 링이 63px이 된다."""
    for size in (30, 63, 84):
        assert render_ring(size, 42.0, theme.YELLOW, width=8).size == (size, size)


def test_color_is_honored():
    assert _rgb(theme.RED) in _colors(ring(80.0, theme.RED))
