"""위젯 조각. 창 없이 픽셀만 잰다.

캔버스 create_rectangle·create_oval에는 안티앨리어싱이 없어(ring_render 머리말)
둥근 모서리와 작은 원이 픽셀 계단으로 드러난다. 그래서 크게 그려 축소한다 —
이 테스트는 그 축소가 실제로 중간톤을 만들어내는지 잰다.
"""

from claude_usage_overlay import theme
from claude_usage_overlay.ring_render import _rgb
from claude_usage_overlay.widget_paint import circle, rounded_box


def test_the_box_is_exactly_the_requested_size():
    """치수가 어긋나면 배율 있는 PC에서 위젯이 서로 안 맞는다."""
    assert rounded_box(16, 16, 4, fill=theme.GREEN).size == (16, 16)
    assert rounded_box(120, 6, 3, fill=theme.YELLOW).size == (120, 6)


def test_the_middle_of_a_filled_box_is_the_fill_color():
    img = rounded_box(16, 16, 4, fill=theme.GREEN)
    assert img.getpixel((8, 8))[:3] == _rgb(theme.GREEN)


def test_the_corner_is_a_blend_not_a_staircase():
    """축소가 곧 안티앨리어싱이다. 모서리에 배경도 채움도 아닌 색이 있어야 한다."""
    img = rounded_box(16, 16, 5, fill=theme.GREEN)
    corner = [img.getpixel((x, y))[:3] for x in range(6) for y in range(6)]
    blends = [c for c in corner if c != _rgb(theme.GREEN) and c != _rgb(theme.BG)]
    assert blends, "중간톤이 하나도 없다 — 축소가 안 걸렸다"


def test_an_outline_only_box_keeps_the_background_inside():
    """꺼진 체크박스는 테두리만 그린다. 안이 칠해지면 켜진 것과 구분이 안 된다."""
    img = rounded_box(16, 16, 4, outline=theme.TEXT_DIM, width=1)
    assert img.getpixel((8, 8))[:3] == _rgb(theme.BG)
    edge = [img.getpixel((x, 8))[:3] for x in range(3)]
    assert any(c != _rgb(theme.BG) for c in edge), "테두리가 안 보인다"


def test_the_circle_is_round_not_square():
    """손잡이가 사각형이면 슬라이더가 아니라 스크롤바로 보인다."""
    img = circle(14, theme.YELLOW)
    assert img.getpixel((7, 7))[:3] == _rgb(theme.YELLOW)
    assert img.getpixel((0, 0))[:3] == _rgb(theme.BG)


def test_the_background_is_opaque():
    """어두운 창 위에 얹으므로 알파 합성을 Tk에 맡기지 않는다.
    ring_render가 RGBA 대신 불투명 bg를 쓰는 것과 같은 이유다."""
    assert rounded_box(16, 16, 4, fill=theme.GREEN).mode == "RGB"
    assert circle(14, theme.YELLOW).mode == "RGB"


def test_a_custom_background_is_honored():
    """드롭다운 목록은 창 배경이 아니라 자기 패널 위에 그린다."""
    img = rounded_box(16, 16, 4, fill=theme.GREEN, bg=theme.RING_TRACK)
    assert img.getpixel((0, 0))[:3] == _rgb(theme.RING_TRACK)
