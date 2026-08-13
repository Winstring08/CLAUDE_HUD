"""오버레이에 그려질 문구가 창 안에 실제로 들어가는지 잰다.

창을 띄우지 않는다. 글꼴 폭만 재므로 UI 테스트가 아니다.
이게 없으면 문구를 한 글자 늘렸을 때 조용히 잘리고, 하필 잘리는 것이
사용자가 조치해야 하는 RELOGIN·RATE_LIMITED 상태다.

**RELOGIN 문구는 리터럴로 베끼지 않고 credentials에서 가져온다.** 손으로
베끼면 문구가 바뀌었을 때 테스트만 옛날 것을 재고, 정작 화면에 가는
문자열은 아무도 안 잰다.

**LINE1·LINE2와 창 폭 190px은 자세히 모드 근거다.**

Tk 루트는 conftest.py의 세션 픽스처를 쓴다 — 모듈마다 만들면 두 번째 것이
이 환경에서 죽는다 (그쪽 머리말에 실측이 있다).
"""

import tkinter.font as tkfont

import pytest

from claude_usage_overlay import formatting as fmt
from claude_usage_overlay import overlay as ov
from claude_usage_overlay.credentials import RELOGIN_MSG, STALE_TOKEN_MSG

# RELOGIN detail은 "제목 — 할 일" 한 문자열이고 오버레이가 두 줄로 쪼갠다.
RELOGIN_HEADS = [m.partition(" — ")[0] for m in (RELOGIN_MSG, STALE_TOKEN_MSG)]
RELOGIN_TAILS = [m.partition(" — ")[2] for m in (RELOGIN_MSG, STALE_TOKEN_MSG)]

# 스펙 7장의 다섯 상태에 실제로 들어가는 문구 전부.
# 문구를 늘리려면 여기도 늘리고, 테스트가 통과하는지 본다.
#
# snapshot이 없을 때는 detail이 **첫 줄**에 그려진다. 그래서 폴러가 만드는
# detail 문구가 line2가 아니라 line1 목록에 들어간다 — 글꼴이 1px 더 크다.
# 상태 문구는 리터럴로 베끼지 않고 formatting에서 가져온다. 손으로 베끼면
# 문구를 고쳤을 때 테스트만 옛 문자열을 재고, 정작 화면에 가는 것은 안 잰다.
LINE1 = [
    "10시간 14분 후 리셋",   # format_countdown 최장
    "곧 리셋",
    fmt.NO_RESET_TEXT,
    fmt.LOADING_TEXT,         # 폴러 초기 상태
    fmt.NO_DATA_TEXT,         # 한 번도 성공하지 못한 채 실패
    fmt.AUTH_RETRY_TEXT,      # 401 유예 구간
    fmt.SCHEMA_ERROR_TEXT,
    fmt.RATE_LIMITED_TEXT,    # 첫 조회부터 429면 이것도 첫 줄에 온다
] + RELOGIN_HEADS
LINE2 = RELOGIN_TAILS + [
    fmt.RATE_LIMITED_TEXT,
    "120분째 갱신 실패",
    "23시간 전 갱신",
    "방금 갱신됨",
]


def _fits(root, px, text):
    """이 PC에서 쓰일 글꼴과 폴백 글꼴, **둘 다**로 재서 넓은 쪽을 본다.

    같은 문구라도 글꼴에 따라 폭이 다르다 — "10시간 14분 후 리셋"이
    Pretendard로는 169px, Segoe UI로는 181px이다. 한쪽으로만 재면 Pretendard가
    깔린 PC에서 통과한 창 폭이 안 깔린 PC에서 문구를 잘라먹는다.
    """
    families = {ov.pick_font_family(root), ov.FALLBACK_FAMILY}
    used = max(
        ov.BASE_TEXT_X
        + tkfont.Font(root=root, family=family, size=-px).measure(text)
        + ov.BASE_RIGHT_MARGIN
        for family in families
    )
    return used <= ov.BASE_WIDTH, used


@pytest.mark.parametrize("text", LINE1)
def test_line1_fits(root, text):
    ok, used = _fits(root, ov.BASE_FONT_LINE1_PX, text)
    assert ok, f"{used}px 필요 / 창 폭 {ov.BASE_WIDTH}px — {text!r}"


@pytest.mark.parametrize("text", LINE2)
def test_line2_fits(root, text):
    ok, used = _fits(root, ov.BASE_FONT_LINE2_PX, text)
    assert ok, f"{used}px 필요 / 창 폭 {ov.BASE_WIDTH}px — {text!r}"


def test_only_an_installed_family_is_chosen(root):
    """Tk는 없는 글꼴을 조용히 기본 글꼴로 바꿔 그린다.

    그래서 설치 여부를 확인하지 않으면 화면은 그럴듯한데 창 폭을 역산한
    근거가 엉뚱한 글꼴 것이 된다. 넘치는 문구는 경고 없이 잘린다.
    """
    installed = {name.lower() for name in tkfont.families(root=root)}
    assert ov.pick_font_family(root).lower() in installed


def test_a_family_nobody_has_falls_back(root):
    assert ov.pick_font_family(root, ("이런글꼴은없다",)) == ov.FALLBACK_FAMILY


def test_pretendard_wins_when_it_is_installed(root):
    """설치돼 있으면 Segoe UI보다 앞선다 — 한글까지 한 글꼴로 덮기 위해서다."""
    installed = {name.lower() for name in tkfont.families(root=root)}
    if "pretendard" not in installed:
        pytest.skip("Pretendard가 설치돼 있지 않다")
    assert ov.pick_font_family(root).lower().startswith("pretendard")


def test_ring_number_fits_inside_the_ring(root):
    """링 안에는 숫자만 넣는다(% 없음). 그만큼 키웠으니 넘치지 않는지 잰다.

    100%는 세 자리라 가장 빡빡하다. 넘치면 create_text가 말없이 잘라낸다.
    """
    inner = (ov.BASE_RING_BOX[2] - ov.BASE_RING_BOX[0]) - 2 * ov.BASE_RING_WIDTH
    family = ov.pick_font_family(root)

    for text in ("8", "62", "100"):
        px = ov.BASE_FONT_PCT_PX
        font = tkfont.Font(root=root, family=family, size=-px, weight="bold")
        while px > 8 and font.measure(text) > inner - ov.PCT_INNER_MARGIN * 2:
            px -= 1
            font = tkfont.Font(root=root, family=family, size=-px, weight="bold")
        assert font.measure(text) <= inner - ov.PCT_INNER_MARGIN * 2, text
        assert px >= 12, f"{text!r}가 {px}px까지 줄었다 — 링이 너무 작다"


def test_ring_number_fits_in_the_basic_mode_ring(root):
    """기본 모드는 링 안쪽이 40px이라 사용량을 18px로, 남은 시간을 15px로 시작한다.

    배율 셋과 글꼴 둘을 모두 재는 이유는 스펙 2.5절의 실측 때문이다 — 125%의
    `5:20`은 42px, 150%의 `100`은 49px로 가용폭을 넘는다. 줄이는 루프를 거친
    뒤의 크기를 잰다.
    """
    families = {ov.pick_font_family(root), ov.FALLBACK_FAMILY}
    cases = (
        ("62", ov.SMALL_FONT_PCT_PX),
        ("100", ov.SMALL_FONT_PCT_PX),
        ("5:20", ov.SMALL_FONT_TIME_PX),
        ("0:27", ov.SMALL_FONT_TIME_PX),
        ("10:14", ov.SMALL_FONT_TIME_PX),
    )
    for scale in (1.0, 1.25, 1.5):
        limit = ov.ring_text_limit(ov.SMALL_RING_BOX, ov.SMALL_RING_WIDTH, scale)
        for text, start in cases:
            for family in families:
                px = round(start * scale)
                font = tkfont.Font(root=root, family=family, size=-px, weight="bold")
                while px > ov.MIN_RING_FONT_PX and font.measure(text) > limit:
                    px -= 1
                    font = tkfont.Font(root=root, family=family, size=-px, weight="bold")
                assert font.measure(text) <= limit, (text, family, scale)
                assert px > ov.MIN_RING_FONT_PX, (
                    f"{text!r}가 바닥({px}px)까지 줄었다 — 링이 너무 작다"
                )


def test_font_sizes_are_pixels_not_points():
    """Tk에서 양수 크기는 포인트다. 포인트는 tk scaling이 이미 DPI로
    확대하므로, 거기에 dpi_scale()을 또 곱하면 고배율에서 이중 확대된다."""
    assert all(spec[1] < 0 for spec in ov.fonts_for(1.0).values())
    assert all(spec[1] < 0 for spec in ov.fonts_for(1.5).values())


def test_font_sizes_scale_with_dpi():
    """캔버스 치수와 같은 배율로 커져야 글자가 창을 넘지 않는다."""
    base, high = ov.fonts_for(1.0), ov.fonts_for(1.5)
    for key in base:
        assert high[key][1] == -round(-base[key][1] * 1.5)
