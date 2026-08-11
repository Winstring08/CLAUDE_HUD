"""잉크 중앙 정렬. 창을 띄우지 않고 재는 것들이다.

Tk 인스턴스가 필요한 것은 ascent 하나뿐이고, 나머지는 PIL과 순수 산수다.
"""

import tkinter as tk
import tkinter.font as tkfont

import pytest

from claude_usage_overlay import text_center
from claude_usage_overlay.font_install import font_file_for
from claude_usage_overlay.text_center import Ink, center_start, measure_ink, nw_xy


@pytest.fixture(scope="module")
def root():
    r = tk.Tk()
    r.withdraw()
    yield r
    r.destroy()


def test_the_spare_half_pixel_goes_up():
    """40px 상자에 13px 잉크를 넣으면 위 13 · 아래 14다. 아래로 보내면 처져 보인다
    (스펙 2.6절 육안 확인)."""
    assert center_start(40, 13) == 13


def test_center_start_uses_floor_not_bankers_rounding():
    """파이썬 round()는 은행가 반올림이라 round(1.5)=2(아래)·round(2.5)=2(위)로
    값의 홀짝에 따라 방향이 갈린다. floor여야 항상 위로 간다."""
    for box, ink in ((40, 13), (40, 11), (33, 12), (33, 10), (48, 21)):
        spare = box - ink
        start = center_start(box, ink)
        assert start == spare // 2
        assert spare - start >= start, f"({box}, {ink}) — 아래 여백이 더 커야 한다"


def test_margins_never_differ_by_more_than_a_pixel():
    for box in range(20, 60):
        for ink in range(5, box):
            start = center_start(box, ink)
            assert abs((box - ink - start) - start) <= 1


def test_measure_ink_is_relative_to_the_baseline():
    """숫자는 baseline에 붙어 있으므로 bottom이 0이다. top은 음수(위쪽)다."""
    ink = measure_ink(font_file_for("Pretendard", bold=True), 18, "100")
    assert ink is not None
    assert ink.bottom == 0
    assert ink.top == -13, "스펙 2.6절: 18px 숫자의 잉크는 13px"


def test_measure_ink_gives_up_on_a_missing_file(tmp_path):
    assert measure_ink(tmp_path / "nope.ttf", 18, "100") is None


def test_nw_xy_reproduces_the_measured_ink_position(root):
    """스펙 2.6절이 화면을 캡처해 픽셀을 센 결과와 맞는지 본다.

    Pretendard 18px `100`, 링 안쪽 상자 top=13 · 높이 40에서 잉크가 26~38을
    덮었고 위 여백 13 · 아래 여백 14였다.
    """
    font = tkfont.Font(root=root, family="Pretendard", size=-18, weight="bold")
    if font.actual("family").lower() != "pretendard":
        pytest.skip("Pretendard가 이 프로세스에 올라와 있지 않다")

    ink = measure_ink(font_file_for("Pretendard", bold=True), 18, "100")
    _x, y = nw_xy((13, 13, 53, 53), ink, font.metrics("ascent"))

    ink_top = y + font.metrics("ascent") + ink.top
    ink_bottom = y + font.metrics("ascent") + ink.bottom
    assert (ink_top, ink_bottom) == (26, 39)      # 픽셀 26~38을 덮는다
    assert (ink_top - 13, 52 - (ink_bottom - 1)) == (13, 14)


@pytest.mark.parametrize("scale", (1.0, 1.25, 1.5))
@pytest.mark.parametrize("text", ("62", "100", "5:20", "0:27", "10:14"))
def test_ink_is_centered_at_every_scale(root, scale, text):
    """스펙 14장이 실측하지 않은 채로 남긴 축이다. 잉크를 매번 재는 방식이므로
    맞을 것으로 봤지만 확인이 필요하다고 적혀 있었다 — 여기서 확인한다.

    위·아래 여백 차이가 1px 이하이고 남는 반 픽셀이 **위로** 간다.
    """
    box_top = round(13 * scale)
    box_size = round(40 * scale)
    px = round(18 * scale)
    path = font_file_for("Pretendard", bold=True)
    font = tkfont.Font(root=root, family="Pretendard", size=-px, weight="bold")
    if font.actual("family").lower() != "pretendard":
        pytest.skip("Pretendard가 이 프로세스에 올라와 있지 않다")

    ink = measure_ink(path, px, text)
    _x, y = nw_xy((box_top, box_top, box_top + box_size, box_top + box_size), ink,
                  font.metrics("ascent"))
    ink_top = y + font.metrics("ascent") + ink.top
    ink_h = ink.bottom - ink.top

    above = ink_top - box_top
    below = box_size - ink_h - above
    assert abs(above - below) <= 1, f"위 {above} / 아래 {below}"
    assert above <= below, "남는 반 픽셀은 위로 보낸다"


def test_a_glyph_off_the_baseline_is_still_centered():
    """`—`는 baseline 위에 떠 있다. resets_at이 없을 때 링 안에 오는 문구다.
    baseline만 맞추면 처져 보이므로 잉크로 맞춰야 한다."""
    ink = Ink(left=0, right=20, top=-12, bottom=-6)
    _x, y = nw_xy((0, 0, 40, 40), ink, 20)
    ink_top = y + 20 + ink.top
    assert ink_top == center_start(40, 6)
