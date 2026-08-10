"""HudState → 16×16 트레이 아이콘. 순수 함수라 UI 없이 테스트할 수 있다.

수위 경계에서 숫자 색을 반전시킨다. PIL에는 클리핑이 없으므로
밝은 글자 레이어와 어두운 글자 레이어를 따로 그린 뒤 수위선을 기준으로
잘라 합성한다.
"""

from PIL import Image, ImageDraw, ImageFont

from . import theme, winmetrics
from .models import HudState, Status

# 앞에서부터 있는 것을 쓴다. 시스템 Fonts와 사용자 Fonts 양쪽을 본다.
FONT_FILES = [
    "Pretendard-Bold.ttf",
    "Pretendard-SemiBold.ttf",
    "PretendardVariable.ttf",
    "segoeuib.ttf",
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


TEXT_RATIO = 0.72   # 아이콘 높이 대비 글자 크기의 출발점
SIDE_MARGIN = 2     # 좌우로 이만큼은 남긴다


def _fitted_font(draw, size: int, text: str):
    """아이콘 폭에 실제로 들어가는 가장 큰 글꼴.

    글꼴마다 같은 크기라도 폭이 다르다 — 16px 아이콘에서 두 자리 숫자는
    Segoe UI로는 여유가 있지만 Pretendard로는 좌우가 꽉 찬다. 비율을
    하나로 못박으면 글꼴을 바꿀 때마다 이 자리가 조용히 깨지므로,
    넘치지 않을 때까지 1px씩 줄여서 고른다.
    """
    px = max(6, int(size * TEXT_RATIO))
    font = _font(px)
    while px > 6:
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= size - SIDE_MARGIN * 2:
            break
        px -= 1
        font = _font(px)
    return font


def _centered_text(size: int, text: str, color: str) -> Image.Image:
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    font = _fitted_font(draw, size, text)
    box = draw.textbbox((0, 0), text, font=font)
    x = (size - (box[2] - box[0])) / 2 - box[0]
    y = (size - (box[3] - box[1])) / 2 - box[1]
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
    fill_color = theme.color_for(pct, warn, danger)

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

    # 숫자를 두 번 그리고 수위선에서 잘라 합친다
    text = str(int(round(pct)))
    light = _centered_text(size, text, theme.TEXT_LIGHT)
    dark = _centered_text(size, text, theme.TEXT_DARK)

    above = Image.new("L", (size, size), 0)
    ImageDraw.Draw(above).rectangle([(0, 0), (size, fill_top)], fill=255)
    below = Image.new("L", (size, size), 0)
    ImageDraw.Draw(below).rectangle([(0, fill_top), (size, size)], fill=255)

    img.paste(light, (0, 0), Image.composite(light.getchannel("A"), above.point(lambda _: 0), above))
    img.paste(dark, (0, 0), Image.composite(dark.getchannel("A"), below.point(lambda _: 0), below))

    return _dim(img) if state.status in DIM_STATUSES else img
