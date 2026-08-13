from claude_usage_overlay import theme


def test_below_warn_is_green():
    assert theme.color_for(0) == theme.GREEN
    assert theme.color_for(69.9) == theme.GREEN


def test_warn_band_is_yellow():
    assert theme.color_for(70) == theme.YELLOW
    assert theme.color_for(89.9) == theme.YELLOW


def test_danger_band_is_red():
    assert theme.color_for(90) == theme.RED
    assert theme.color_for(100) == theme.RED


def test_custom_thresholds_are_honored():
    assert theme.color_for(55, warn=50, danger=80) == theme.YELLOW
    assert theme.color_for(85, warn=50, danger=80) == theme.RED


def _rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def _luminance(hex_color):
    def channel(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in _rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b):
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# 스펙 7장의 표. **눈으로 고른 값이라 재현 규칙이 없다** — 명도를 몇 % 옮겼다는
# 서술은 근사일 뿐이고 정본은 이 hex다.
CHOSEN = {
    "GREEN": "#69ba7a",
    "YELLOW": "#f4b044",
    "RED": "#e8696b",
    "FILL_GREEN": "#449354",
    "FILL_YELLOW": "#c9800c",
    "FILL_RED": "#dc2224",
}

# 견본 그대로 쓰면 노란 구간이 여기까지 떨어진다 (스펙 2.7절 실측).
RAW_SAMPLE_YELLOW_CONTRAST = 1.71


def test_the_colors_are_the_ones_that_were_chosen_by_eye():
    """트레이에 세 팔레트를 동시에 띄워 비교한 뒤 정한 값이다. 계산으로 다시
    만들어낼 수 없으므로 여기 적어 묶어둔다."""
    for name, value in CHOSEN.items():
        assert getattr(theme, name) == value, name


def test_white_numbers_stay_readable_on_every_fill():
    """트레이 아이콘은 채움 위에 흰 숫자를 얹는다. 견본(#f3a72e)을 그대로 쓰면
    1.71:1까지 떨어져 기존 theme.py 주석이 "사실상 읽히지 않는다"고 적어둔
    구간에 들어간다. 어둡게 한 뒤에는 2.69:1이다 (스펙 2.7절)."""
    for name in ("FILL_GREEN", "FILL_YELLOW", "FILL_RED"):
        got = _contrast(getattr(theme, name), theme.TEXT_LIGHT)
        assert got > RAW_SAMPLE_YELLOW_CONTRAST + 0.9, f"{name}: {got:.2f}"


def test_ring_is_brighter_than_the_matching_fill():
    """한 색의 밝기 두 단계다. 링은 어두운 창 위의 5px 선이라 밝아야 하고,
    채움은 흰 숫자를 얹는 바탕이라 어두워야 한다."""
    for ring, fill in (
        (theme.GREEN, theme.FILL_GREEN),
        (theme.YELLOW, theme.FILL_YELLOW),
        (theme.RED, theme.FILL_RED),
    ):
        assert _luminance(ring) > _luminance(fill), f"{ring} vs {fill}"


def test_ring_stays_visible_on_the_window_background():
    """5px 선이라 4.0:1이면 충분하다. 이 아래로 내려가면 노란 링이 배경에 묻힌다."""
    for ring in (theme.GREEN, theme.YELLOW, theme.RED):
        assert _contrast(ring, theme.BG) >= 4.0, ring
