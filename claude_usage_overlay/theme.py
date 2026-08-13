"""사용률 → 색. 오버레이와 트레이 아이콘이 같은 함수를 쓴다."""

# 링 색과 채움 색은 **같은 견본의 밝기 두 단계**다. 견본은 #4ca45e · #f3a72e ·
# #e3484a 셋이고, 색상과 채도는 건드리지 않고 명도만 옮겼다 (HSL 채도 실측:
# 초록 36.7 → 37.0 → 36.7, 노랑 89.1 → 88.9 → 88.7, 빨강 73.5 → 73.4 → 73.2).
#
# 여기(링)는 견본에서 **밝힌** 쪽이다. 어두운 창 위에 그리는 5px 선이라
# 밝아야 보인다. 눈으로 고른 값이라 "명도 +30%" 같은 재현 규칙은 없다 —
# 정본은 이 hex다.
GREEN = "#69ba7a"
YELLOW = "#f4b044"
RED = "#e8696b"
GREY = "#4a4a52"
BG = "#262b36"
TEXT_LIGHT = "#e8ecf2"
TEXT_DARK = "#0f1115"
TEXT_DIM = "#8b8b93"   # 보조 문구와 "아직 값이 없음" 기호

RING_TRACK = "#333845"   # 링의 빈 부분
RING_DIM = "#3a3f4b"     # 값이 낡았을 때의 링 색
TEXT_DIM_RING = "#6d7280"  # 값이 낡았을 때의 숫자·첫 줄


# 여기(채움)는 견본에서 **어둡게 한** 쪽이다. 흰 숫자를 얹는 바탕이라 어두워야
# 읽힌다 — 밝은 채움 위의 흰 글자는 대비가 1.7까지 떨어져 사실상 안 읽힌다.
# 트레이에 세 팔레트를 동시에 띄워 비교한 뒤 정했다 (스펙 2.7절).
FILL_GREEN = "#449354"
FILL_YELLOW = "#c9800c"
FILL_RED = "#dc2224"


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
