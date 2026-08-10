"""HudState → 16×16 트레이 아이콘. 순수 함수라 UI 없이 테스트할 수 있다.

**숫자는 항상 흰색 하나다.** 예전에는 수위 경계에서 색을 뒤집었는데,
16px에서는 한 숫자가 위아래로 쪼개져 오히려 읽기 어려웠다 — 흰 부분만
글자로 보이고 나머지는 배경에 묻힌다.

그래서 색을 나누는 대신 채움을 어둡게 골랐다. theme.FILL_* 는 채도를 94%
이상 유지한 채 명도만 낮춘 값이고, 그 위에서 흰 숫자가 항상 이긴다.
"""

from PIL import Image, ImageDraw, ImageFont

from . import theme, winmetrics
from .models import HudState, Status

# 앞에서부터 있는 것을 쓴다. 시스템 Fonts와 사용자 Fonts 양쪽을 본다.
#
# **오버레이와 달리 여기는 Segoe UI가 먼저다.** 아이콘에 들어가는 글자는
# 숫자와 ✕·!·?·… 뿐이라 한글이 없고, 그러면 Pretendard를 쓸 이유가 사라진다.
# 오히려 손해다 — 16px에서 "42"의 폭이 Segoe UI Bold는 11px 크기에 12px인데
# Pretendard Bold는 15px이라(실측), 같은 자리에 넣으려면 8px까지 줄여야 하고
# 그러면 트레이에서 숫자를 읽을 수 없다. 작은 크기 가독성은 윈도우 UI용으로
# 힌팅된 Segoe UI 쪽이 낫다. Pretendard는 Segoe UI가 없는 환경의 대비책으로만 남긴다.
FONT_FILES = [
    "segoeuib.ttf",
    "Pretendard-Bold.ttf",
    "malgunbd.ttf",
    "arialbd.ttf",
]
STALE_ALPHA = 115  # 255의 약 45%
LOADING_TEXT = "…"  # 아직 값이 없음. SCHEMA_ERROR의 "?"와 구분된다

# 값이 낡은 상태. 둘 다 "기다리면 낫는다"이므로 같은 흐림으로 그린다.
DIM_STATUSES = frozenset({Status.STALE, Status.RATE_LIMITED})


def _hex(color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    color = color.lstrip("#")
    return (int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16), alpha)


def _font(size: int):
    """FONT_FILES 순서가 디렉터리 순서보다 우선한다.

    디렉터리를 바깥 루프에 두면, 사용자 Fonts에 있는 Pretendard보다 시스템
    Fonts의 segoeuib가 먼저 잡혀 우선순위가 뒤집힌다.
    """
    for name in FONT_FILES:
        for directory in (winmetrics.fonts_dir(), winmetrics.user_fonts_dir()):
            try:
                return ImageFont.truetype(str(directory / name), size)
            except OSError:
                continue
    return ImageFont.load_default()


# 아이콘 높이 대비 글자 크기. 16px에서 13px이 나오고, 그게 두 자리 숫자가
# 들어가는 최대다(실측: 13px에서 "42" 폭 14px, 14px로 올리면 16px이 되어 넘친다).
# 게이지는 숫자 뒤에 깔리는 배경 채움이라 글자와 자리를 다투지 않는다 —
# 이 비율을 제한하는 것은 아이콘 폭 하나뿐이다.
TEXT_RATIO = 0.82
SIDE_MARGIN = 1     # 좌우로 이만큼은 남긴다
MIN_TEXT_PX = 9     # 이보다 작으면 트레이에서 읽을 수 없다


def _fitted_font(draw, size: int, text: str):
    """아이콘 폭에 실제로 들어가는 가장 큰 글꼴.

    글꼴마다 같은 크기라도 폭이 다르다. 비율을 하나로 못박으면 글꼴을 바꿀 때
    이 자리가 조용히 깨지므로, 넘치지 않을 때까지 1px씩 줄여서 고른다.

    **단 MIN_TEXT_PX 아래로는 줄이지 않는다.** 넘치는 것보다 읽을 수 없는 것이
    더 나쁘다 — 트레이 아이콘은 사용률을 한눈에 보라고 있는 물건이고, 8px로
    그린 숫자는 그 목적을 통째로 잃는다. 여기 걸리면 글자가 가장자리에 닿을
    수는 있어도 크기는 지킨다.
    """
    px = max(MIN_TEXT_PX, int(size * TEXT_RATIO))
    font = _font(px)
    while px > MIN_TEXT_PX:
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= size - SIDE_MARGIN * 2:
            break
        px -= 1
        font = _font(px)
    return font


def _centered_text(size: int, text: str, color: str) -> Image.Image:
    """글자는 **안티앨리어싱을 켜고** 그린다 (PIL 기본값).

    끄는 쪽도 만들어 트레이에 나란히 띄워 비교했고, 켠 쪽이 낫다는 결론이
    나왔다. 토글 상수를 두지 않는 이유는 한 번 어긋난 적이 있어서다 —
    상수는 False인데 비교 이미지는 True로 렌더해 놓고 결론만 반영하지
    않으면, 화면과 코드가 조용히 갈라진다.
    """
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    font = _fitted_font(draw, size, text)
    box = draw.textbbox((0, 0), text, font=font)
    # 좌표를 정수로 맞춘다. 반 픽셀 어긋난 자리에 그리면 안티앨리어싱을 꺼도
    # 획이 인접 픽셀로 번지거나 한쪽으로 쏠린다.
    x = round((size - (box[2] - box[0])) / 2 - box[0])
    y = round((size - (box[3] - box[1])) / 2 - box[1])
    draw.text((x, y), text, font=font, fill=_hex(color))
    return layer


def _base(size: int, bg: str) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle(
        [(0, 0), (size - 1, size - 1)], radius=max(2, size // 5), fill=_hex(bg)
    )
    return img


def _symbol_icon(size: int, bg: str, text: str, fg: str) -> Image.Image:
    img = _base(size, bg)
    return Image.alpha_composite(img, _centered_text(size, text, fg))


def _cross_icon(size: int, bg: str) -> Image.Image:
    img = _base(size, bg)
    draw = ImageDraw.Draw(img)
    pad = size * 0.31
    width = max(2, size // 8)
    draw.line([(pad, pad), (size - pad, size - pad)], fill=_hex("#2a0d0d"), width=width)
    draw.line([(size - pad, pad), (pad, size - pad)], fill=_hex("#2a0d0d"), width=width)
    return img


def _dim(img: Image.Image) -> Image.Image:
    alpha = img.getchannel("A").point(lambda v: min(v, STALE_ALPHA))
    img.putalpha(alpha)
    return img


def render_icon(
    state: HudState, size: int | None = None, warn: int = 70, danger: int = 90
) -> Image.Image:
    # 배율 100%면 16, 150%면 24. 하드코딩하지 않는다.
    size = size or winmetrics.system_icon_size()

    if state.status is Status.RELOGIN:
        return _symbol_icon(size, theme.GREY, "!", theme.RED)

    if state.status is Status.SCHEMA_ERROR:
        return _symbol_icon(size, theme.GREY, "?", theme.TEXT_LIGHT)

    if state.snapshot is None:
        # 아직 보여줄 값이 없다 — 첫 조회 전이거나 한 번도 성공하지 못했다.
        # 여기서 "?"를 쓰면 프로그램을 켤 때마다 몇 초 동안 "데이터 형식이
        # 바뀜" 기호가 뜬다. 폴러의 초기 상태가 (STALE, None)이기 때문이다.
        return _symbol_icon(size, theme.GREY, LOADING_TEXT, theme.TEXT_DIM)

    pct = max(0.0, min(100.0, state.snapshot.five_hour_pct))
    # 링과 다른 색표를 쓴다. 여기는 흰 숫자를 얹을 배경이라 어두워야 한다.
    fill_color = theme.fill_color_for(pct, warn, danger)

    if pct >= 100:
        img = _cross_icon(size, fill_color)
        return _dim(img) if state.status in DIM_STATUSES else img

    # 배경 + 아래에서 차오르는 채움
    img = _base(size, theme.BG)
    fill_top = size - round(size * pct / 100.0)
    if fill_top < size:
        fill_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(fill_layer).rounded_rectangle(
            [(0, 0), (size - 1, size - 1)], radius=max(2, size // 5), fill=_hex(fill_color)
        )
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).rectangle([(0, fill_top), (size, size)], fill=255)
        img.paste(fill_layer, (0, 0), mask)

    # 숫자는 흰색 하나로 그린다. 배경(어두운 바탕이든 어두운 채움이든)
    # 어디에 얹혀도 대비가 충분하므로 색을 나눌 이유가 없다.
    img = Image.alpha_composite(
        img, _centered_text(size, str(int(round(pct))), theme.TEXT_LIGHT)
    )

    return _dim(img) if state.status in DIM_STATUSES else img
