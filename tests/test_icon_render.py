from datetime import datetime, timedelta, timezone

from claude_usage_overlay.icon_render import render_icon
from claude_usage_overlay.models import HudState, Status, UsageSnapshot

NOW = datetime(2026, 8, 10, 3, 25, tzinfo=timezone.utc)


def state(status, pct=23.0):
    snap = (
        None
        if pct is None
        else UsageSnapshot(pct, NOW + timedelta(hours=2), 15.0, NOW)
    )
    return HudState(status, snap, "")


ICON = 16  # 테스트는 배율에 흔들리지 않도록 항상 크기를 명시한다

# 채움 영역을 찍는 좌표. y=15가 아니라 y=14인 이유는 라운드 사각형 때문이다 —
# radius가 3이므로 (1, 15)는 모서리 곡선 **바깥**이고 어떤 상태에서도
# (0, 0, 0, 0)이다. 거기서 색을 확인하면 무조건 실패한다. (1, 14)는 곡선 안이다.
FILL_PX = (1, 14)


def test_icon_is_requested_size_and_rgba():
    img = render_icon(state(Status.OK), size=ICON)
    assert img.size == (ICON, ICON)
    assert img.mode == "RGBA"


def test_renders_at_high_dpi_sizes_too():
    """배율 125%·150% PC에서는 트레이 아이콘이 20px·24px이다."""
    for size in (20, 24, 32):
        img = render_icon(state(Status.OK, 23.0), size=size)
        assert img.size == (size, size)


def test_default_size_follows_system_metric():
    from claude_usage_overlay import winmetrics

    img = render_icon(state(Status.OK, 23.0))
    assert img.size == (winmetrics.system_icon_size(),) * 2


def _rgb_of(color: str):
    color = color.lstrip("#")
    return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))


def test_low_usage_fills_bottom_with_the_ok_color():
    """색은 theme에서 가져와 비교한다. 임계값을 손으로 적으면 색을 바꿀 때
    테스트만 옛 값을 재고, 정작 화면에 나가는 색은 아무도 안 본다."""
    from claude_usage_overlay import theme

    img = render_icon(state(Status.OK, 23.0), size=ICON)
    assert img.getpixel(FILL_PX)[:3] == _rgb_of(theme.FILL_GREEN)
    assert img.getpixel((1, 1))[:3] == _rgb_of(theme.BG), "꼭대기는 빈 영역이다"


def test_warn_band_fills_the_warn_color():
    from claude_usage_overlay import theme

    img = render_icon(state(Status.OK, 75.0), size=ICON)
    assert img.getpixel(FILL_PX)[:3] == _rgb_of(theme.FILL_YELLOW)


def test_danger_band_fills_the_danger_color():
    from claude_usage_overlay import theme

    img = render_icon(state(Status.OK, 95.0), size=ICON)
    assert img.getpixel(FILL_PX)[:3] == _rgb_of(theme.FILL_RED)


MIN_FILL_CONTRAST = 2.5


def test_fill_colors_keep_white_text_readable():
    """흰 숫자를 얹을 배경이므로 명도 대비에 하한을 둔다.

    지금 값(초록 3.2 · 주황 2.7 · 빨강 4.1)은 색감을 우선해 고른 것이라
    일반 권장선인 4.5에는 못 미친다. 그래서 여기서 지키는 것은 "가장 좋은
    대비"가 아니라 **더 나빠지지 않는 것**이다 — 원래의 밝은 색으로
    되돌리면 1.3~1.8까지 떨어져 숫자가 배경에 통째로 묻힌다.
    """
    from claude_usage_overlay import theme

    def luminance(color):
        parts = [v / 255 for v in _rgb_of(color)]
        parts = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in parts]
        return 0.2126 * parts[0] + 0.7152 * parts[1] + 0.0722 * parts[2]

    def contrast(a, b):
        la, lb = luminance(a), luminance(b)
        hi, lo = max(la, lb), min(la, lb)
        return (hi + 0.05) / (lo + 0.05)

    for fill in (theme.FILL_GREEN, theme.FILL_YELLOW, theme.FILL_RED):
        got = contrast(theme.TEXT_LIGHT, fill)
        assert got >= MIN_FILL_CONTRAST, f"{fill} 위 흰 글자 대비가 {got:.1f}로 너무 낮다"


def test_digits_are_antialiased():
    """확정 사항이다. 켠 쪽과 끈 쪽을 트레이에 나란히 띄워 비교해 골랐다.

    끄면 글자 픽셀이 검·흰 두 값만 남아 이미지 전체 색상 수가 한 자리로
    떨어진다(실측: 끔 5색 · 켬 50색 안팎). 그 차이로 판정한다.
    """
    img = render_icon(state(Status.OK, 42.0), size=ICON)
    tones = {img.getpixel((x, y))[:3] for y in range(ICON) for x in range(ICON)}
    assert len(tones) > 20, f"색이 {len(tones)}가지뿐 — 안티앨리어싱이 꺼졌다"


def test_digits_are_a_single_colour():
    """수위 경계에서 색을 뒤집지 않는다.

    16px에서는 한 숫자가 위아래로 쪼개져 흰 부분만 글자처럼 보이고
    나머지는 배경에 묻혔다. 숫자 잉크는 흰색 계열 하나여야 한다.
    """
    from claude_usage_overlay import theme

    img = render_icon(state(Status.OK, 62.0), size=ICON)   # 수위가 글자 한가운데
    dark_ink = [
        (x, y)
        for y in range(2, ICON - 2)
        for x in range(3, ICON - 3)
        if sum(img.getpixel((x, y))[:3]) < sum(_rgb_of(theme.BG)) - 40
    ]
    assert not dark_ink, f"어두운 글자 픽셀이 남아 있다: {dark_ink[:5]}"


def test_fill_height_grows_with_usage():
    def filled_rows(pct):
        img = render_icon(state(Status.OK, pct), size=ICON)
        rows = 0
        for y in range(ICON):
            r, g, b, _ = img.getpixel((1, y))
            if r + g + b > 200:              # 배경보다 밝으면 채워진 것
                rows += 1
        return rows

    assert filled_rows(90.0) > filled_rows(20.0)


def test_full_usage_draws_no_digits():
    """100%는 ✕로 대체된다. 숫자가 들어갈 자리가 없다."""
    full = render_icon(state(Status.OK, 100.0), size=ICON)
    partial = render_icon(state(Status.OK, 23.0), size=ICON)
    assert full.tobytes() != partial.tobytes()
    # 배경이 전부 빨강 계열인지 — 모서리 안쪽을 확인
    r, g, b, _ = full.getpixel((2, 2))
    assert r > 200 and g < 180


def _ink_rows(img):
    """글자가 차지하는 세로 범위.

    밝은 픽셀만 세면 안 된다. 숫자는 수위선에서 색이 반전되어 채움 위에서는
    **어두운** 글자로 그려지므로, 42%처럼 수위가 글자 한가운데를 지나면
    아래 절반이 통째로 빠진다. 배경(합 135)과 채움(519~558)은 중간 밝기이고
    글자만 양 극단(밝음 710·어두움 53)이므로 그 둘을 다 센다.

    좌우 3px은 라운드 모서리의 중간톤을 피하려고 뺀다.
    """
    rows = [
        y
        for y in range(img.height)
        for x in range(3, img.width - 3)
        if img.getpixel((x, y))[3] > 200
        and (sum(img.getpixel((x, y))[:3]) > 600 or sum(img.getpixel((x, y))[:3]) < 120)
    ]
    return (min(rows), max(rows)) if rows else None


def test_digits_are_big_enough_to_read():
    """트레이 아이콘은 사용률을 한눈에 보라고 있는 물건이다.

    폭을 맞추겠다고 글자를 8px까지 줄이면 16px 트레이에서 숫자를 읽을 수
    없고, 그러면 아이콘이 존재할 이유가 사라진다. 글꼴을 바꿀 때 이 자리가
    조용히 깨지는 것을 막는 테스트다 — 실제로 한 번 깨뜨렸다.
    """
    for pct in (7.0, 42.0, 88.0):
        span = _ink_rows(render_icon(state(Status.OK, pct), size=ICON))
        assert span is not None, f"{pct}%에서 숫자가 안 보인다"
        height = span[1] - span[0] + 1
        # 기본 글꼴에서 11px 숫자의 잉크 높이는 8px, 즉 아이콘의 50%다.
        assert height >= ICON * 0.4, f"{pct}%의 숫자 높이가 {height}px — 너무 작다"


def test_font_never_shrinks_below_the_readable_floor():
    """폭을 맞추려다 크기를 잃는 일을 막는 바닥선.

    글꼴을 바꾸면 같은 크기라도 폭이 달라진다. Pretendard Bold는 16px 아이콘의
    "42"를 15px 폭으로 그려서(Segoe UI Bold는 12px), 폭만 보고 줄이면 8px까지
    내려간다. 넘치는 것보다 못 읽는 것이 나쁘다.
    """
    from PIL import Image, ImageDraw

    from claude_usage_overlay.icon_render import MIN_TEXT_PX, _fitted_font

    draw = ImageDraw.Draw(Image.new("RGBA", (ICON, ICON)))
    for text in ("7", "42", "88", "…", "?"):
        assert _fitted_font(draw, ICON, text).size >= MIN_TEXT_PX


def test_digits_stay_inside_the_icon():
    """글꼴을 바꾸면 같은 크기라도 폭이 달라진다.

    16px에 두 자리 숫자는 Segoe UI로는 여유가 있지만 Pretendard로는 꽉 찬다.
    가장자리 한 줄에 글자 잉크가 닿으면 잘려 보인다.
    """
    from claude_usage_overlay import theme

    bg = tuple(int(theme.BG.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    for pct in (7.0, 42.0, 88.0, 99.0):
        img = render_icon(state(Status.OK, pct), size=ICON)
        for y in range(2, ICON - 2):
            for x in (0, ICON - 1):
                r, g, b, _a = img.getpixel((x, y))
                # 채움 색이나 배경색일 수는 있어도 밝은 글자 잉크가 있으면 안 된다
                assert not (r > 200 and g > 200 and b > 200), f"{pct}%에서 글자가 가장자리에 닿는다"


def _has_grey_background(img):
    """회색 배경이 실제로 칠해졌는지.

    특정 좌표를 찍지 않는다. 가운데 정렬된 기호(!·?·…)의 크기가 바뀌면
    그 좌표를 덮어버려서, 배경이 멀쩡한데도 테스트가 깨진다.
    """
    from claude_usage_overlay import theme

    grey = tuple(int(theme.GREY.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    return grey in {img.getpixel((x, y))[:3] for y in range(ICON) for x in range(ICON)}


def test_relogin_uses_grey_background():
    assert _has_grey_background(
        render_icon(HudState(Status.RELOGIN, None, "재로그인 필요"), size=ICON)
    )


def test_stale_is_dimmed():
    normal = render_icon(state(Status.OK, 23.0), size=ICON)
    stale = render_icon(state(Status.STALE, 23.0), size=ICON)
    assert stale.getpixel(FILL_PX)[3] < normal.getpixel(FILL_PX)[3]


def test_rate_limited_is_dimmed_too():
    """호출 한도도 '기다리면 낫는다'이므로 STALE과 같은 흐림을 쓴다."""
    normal = render_icon(state(Status.OK, 23.0), size=ICON)
    limited = render_icon(state(Status.RATE_LIMITED, 23.0), size=ICON)
    assert limited.getpixel(FILL_PX)[3] < normal.getpixel(FILL_PX)[3]


def test_schema_error_uses_grey_background():
    img = render_icon(HudState(Status.SCHEMA_ERROR, None, "데이터 형식이 바뀜"), size=ICON)
    assert img.size == (ICON, ICON)
    assert _has_grey_background(img), "값이 없으면 회색이다"


LOADING = HudState(Status.STALE, None, "불러오는 중")   # 폴러의 초기 상태 그대로


def test_loading_is_not_drawn_as_a_schema_error():
    """켤 때마다 몇 초씩 "데이터 형식이 바뀜" 기호가 뜨면 안 된다."""
    schema = render_icon(HudState(Status.SCHEMA_ERROR, None, "데이터 형식이 바뀜"), size=ICON)
    assert render_icon(LOADING, size=ICON).tobytes() != schema.tobytes()


def test_loading_uses_grey_background():
    assert _has_grey_background(render_icon(LOADING, size=ICON)), "값이 없으면 회색이다"
