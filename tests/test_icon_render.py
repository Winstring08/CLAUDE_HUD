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


def test_low_usage_fills_bottom_with_green():
    img = render_icon(state(Status.OK, 23.0), size=ICON)
    r, g, b, a = img.getpixel(FILL_PX)       # 바닥 왼쪽 — 채움 영역
    assert g > r and g > b, "바닥은 초록이어야 한다"
    r2, g2, b2, _ = img.getpixel((1, 1))     # 꼭대기 — 빈 영역
    assert g2 < 120, "꼭대기는 어두운 배경이어야 한다"


def test_warn_band_fills_yellow():
    img = render_icon(state(Status.OK, 75.0), size=ICON)
    r, g, b, _ = img.getpixel(FILL_PX)
    assert r > 200 and g > 150 and b < 150, "주의 구간은 노랑이어야 한다"


def test_danger_band_fills_red():
    img = render_icon(state(Status.OK, 95.0), size=ICON)
    r, g, b, _ = img.getpixel(FILL_PX)
    assert r > 200 and g < 180, "위험 구간은 빨강이어야 한다"


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


def test_relogin_uses_grey_background():
    img = render_icon(HudState(Status.RELOGIN, None, "재로그인 필요"), size=ICON)
    r, g, b, _ = img.getpixel((8, 3))
    assert abs(r - g) < 30 and abs(g - b) < 30, "회색이어야 한다"


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
    r, g, b, _ = img.getpixel((8, 3))
    assert abs(r - g) < 30 and abs(g - b) < 30, "값이 없으면 회색이다"


LOADING = HudState(Status.STALE, None, "불러오는 중")   # 폴러의 초기 상태 그대로


def test_loading_is_not_drawn_as_a_schema_error():
    """켤 때마다 몇 초씩 "데이터 형식이 바뀜" 기호가 뜨면 안 된다."""
    schema = render_icon(HudState(Status.SCHEMA_ERROR, None, "데이터 형식이 바뀜"), size=ICON)
    assert render_icon(LOADING, size=ICON).tobytes() != schema.tobytes()


def test_loading_uses_grey_background():
    r, g, b, _ = render_icon(LOADING, size=ICON).getpixel((8, 3))
    assert abs(r - g) < 30 and abs(g - b) < 30, "값이 없으면 회색이다"
