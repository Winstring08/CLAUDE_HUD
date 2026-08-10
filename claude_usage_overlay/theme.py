"""사용률 → 색. 오버레이와 트레이 아이콘이 같은 함수를 쓴다."""

GREEN = "#63e6be"
YELLOW = "#f6c177"
RED = "#ff8f8f"
GREY = "#4a4a52"
BG = "#262b36"
TEXT_LIGHT = "#e8ecf2"
TEXT_DARK = "#0f1115"
TEXT_DIM = "#8b8b93"   # 보조 문구와 "아직 값이 없음" 기호

RING_TRACK = "#333845"   # 링의 빈 부분
RING_DIM = "#3a3f4b"     # 값이 낡았을 때의 링 색
TEXT_DIM_RING = "#6d7280"  # 값이 낡았을 때의 숫자·첫 줄


# 트레이 아이콘 채움 전용 색. 위의 GREEN·YELLOW·RED와 다른 값인 이유는
# 글자와 배경의 관계가 정반대이기 때문이다.
#
#   오버레이 링 — 어두운 창 위에 그리는 얇은 선이라 **밝아야** 보인다
#   아이콘 채움 — 그 위에 흰 숫자를 얹으므로 **어두워야** 숫자가 보인다
#
# 밝은 채움 위의 흰 글자는 명도 대비가 1.3~1.8까지 떨어져 사실상 읽히지 않는다
# (실측). 여기 값들은 채도를 94% 이상으로 유지한 채 명도만 낮춰 고른 것이다 —
# 채도를 깎으면 색만 탁해지고 대비는 거의 오르지 않는다.
FILL_GREEN = "#059669"
FILL_YELLOW = "#d97706"
FILL_RED = "#dc2626"


def color_for(pct: float, warn: int = 70, danger: int = 90) -> str:
    """오버레이 링 색. 어두운 창 위에 그리므로 밝은 쪽을 쓴다."""
    if pct >= danger:
        return RED
    if pct >= warn:
        return YELLOW
    return GREEN


def fill_color_for(pct: float, warn: int = 70, danger: int = 90) -> str:
    """트레이 아이콘 채움 색. 위에 흰 숫자가 얹히므로 어두운 쪽을 쓴다."""
    if pct >= danger:
        return FILL_RED
    if pct >= warn:
        return FILL_YELLOW
    return FILL_GREEN
