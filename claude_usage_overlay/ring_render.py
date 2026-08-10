"""오버레이 링 게이지 이미지. 순수 함수라 창 없이 테스트할 수 있다.

**tkinter Canvas의 create_arc에는 안티앨리어싱이 없다.** Tk 8.6의 한계이고
옵션으로 켤 수도 없어서, 링을 캔버스에 직접 그리면 곡선이 픽셀 계단으로
드러난다. 창 모서리에서 SetWindowRgn을 버린 것과 같은 이유다.

그래서 링만 PIL로 SUPERSAMPLE배 크게 그린 뒤 축소한다. 축소가 곧
안티앨리어싱이다 — 큰 그림의 여러 픽셀이 작은 그림의 한 픽셀로 평균되면서
경계에 중간톤이 생긴다. tests/test_ring_render.py가 그 중간톤의 존재를 잰다.
"""

from PIL import Image, ImageDraw

from . import theme

SUPERSAMPLE = 4      # 4배로 그린 뒤 축소한다. 8배로 올려도 눈에 띄는 차이가 없다
FULL_EXTENT = 359.9  # 360이면 시작과 끝이 겹쳐 이음매가 보인다
START_ANGLE = -90    # PIL은 3시가 0도다. 링은 12시에서 시작해 시계방향으로 돈다


def _rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return (int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16))


def render_ring(
    size: int,
    pct: float,
    color: str,
    bg: str = theme.BG,
    track: str = theme.RING_TRACK,
    width: int = 5,
) -> Image.Image:
    """한 변이 size인 링 이미지. 배경은 bg로 채워 캔버스와 이어지게 한다.

    투명 배경(RGBA) 대신 불투명 bg를 쓰는 이유는 오버레이 캔버스 배경이
    어차피 같은 색이고, 알파 합성을 Tk에 맡기지 않는 편이 결과가 확실해서다.
    """
    s = SUPERSAMPLE
    big = Image.new("RGB", (size * s, size * s), _rgb(bg))
    draw = ImageDraw.Draw(big)

    stroke = max(1, width * s)
    # 선은 경계선 안쪽으로 그려지므로 두께의 절반만큼 들여야 잘리지 않는다.
    inset = stroke // 2 + s
    box = [inset, inset, size * s - inset, size * s - inset]

    draw.arc(box, 0, 360, fill=_rgb(track), width=stroke)

    if pct > 0:
        extent = FULL_EXTENT * min(100.0, pct) / 100.0
        draw.arc(box, START_ANGLE, START_ANGLE + extent, fill=_rgb(color), width=stroke)

    # BOX(단순 평균)를 쓴다. LANCZOS는 선명한 대신 경계 바깥에 밝은 테두리를
    # 남기는데, 어두운 배경 위의 가는 링에서는 그 오버슈트가 눈에 띈다.
    return big.resize((size, size), Image.BOX)
