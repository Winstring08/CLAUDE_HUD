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


def color_for(pct: float, warn: int = 70, danger: int = 90) -> str:
    if pct >= danger:
        return RED
    if pct >= warn:
        return YELLOW
    return GREEN
