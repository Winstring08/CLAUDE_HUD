"""체크박스·슬라이더·드롭다운이 함께 쓰는 PIL 그림 조각.

**스펙 10장의 모듈 표에 없는 파일이다.** 세 위젯이 같은 둥근 사각형을 그리므로
세 번 베끼는 대신 여기 모았다.

캔버스 create_rectangle·create_oval에는 안티앨리어싱이 없다(ring_render 머리말).
둥근 모서리와 작은 원에서 픽셀 계단이 그대로 드러나므로, 링과 트레이 아이콘처럼
SUPERSAMPLE배 크게 그린 뒤 축소한다. 축소가 곧 안티앨리어싱이다.

배경은 투명(RGBA)이 아니라 불투명 bg로 채운다. 설정창 배경이 어차피 한 색이고,
알파 합성을 Tk에 맡기지 않는 편이 결과가 확실하다 — ring_render와 같은 판단이다.
"""

from PIL import Image, ImageDraw

from . import theme
from .ring_render import _rgb

SUPERSAMPLE = 4   # ring_render와 같은 값. 8배로 올려도 눈에 띄는 차이가 없다


def rounded_box(
    w: int,
    h: int,
    radius: int,
    fill: str | None = None,
    outline: str | None = None,
    width: int = 1,
    bg: str = theme.BG,
) -> Image.Image:
    """모서리를 둥글게 깎은 사각형. fill 없이 outline만 주면 테두리만 그린다."""
    s = SUPERSAMPLE
    big = Image.new("RGB", (max(1, w) * s, max(1, h) * s), _rgb(bg))
    stroke = max(1, width * s)
    # 선은 경계선 안쪽으로 그려지므로 두께의 절반만큼 들여야 잘리지 않는다.
    inset = stroke // 2
    ImageDraw.Draw(big).rounded_rectangle(
        [inset, inset, big.width - 1 - inset, big.height - 1 - inset],
        radius=radius * s,
        fill=_rgb(fill) if fill else None,
        outline=_rgb(outline) if outline else None,
        width=stroke,
    )
    # BOX(단순 평균)를 쓴다. LANCZOS는 경계 바깥에 밝은 테두리를 남기는데
    # 어두운 배경 위에서는 그 오버슈트가 눈에 띈다.
    return big.resize((max(1, w), max(1, h)), Image.BOX)


def circle(diameter: int, fill: str, bg: str = theme.BG) -> Image.Image:
    """슬라이더 손잡이. 사각형으로 보이면 스크롤바와 구분이 안 된다."""
    s = SUPERSAMPLE
    d = max(1, diameter)
    big = Image.new("RGB", (d * s, d * s), _rgb(bg))
    ImageDraw.Draw(big).ellipse([0, 0, d * s - 1, d * s - 1], fill=_rgb(fill))
    return big.resize((d, d), Image.BOX)
