"""설정 파일. 깨져 있어도 기본값으로 계속 동작한다."""

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

# 엔드포인트 한도는 측정되지 않았다(스펙 3.2). 8회쯤에서 429가 나고 벌칙이 약 5분이라는
# 것만 안다. 사용자가 이 하한 아래로 내리면 벌칙이 상시화되므로 설정 자유를 여기서 끊는다.
#
# 다만 120이라는 숫자 자체도 측정값이 아니다. '짧은 시간에 8회'의 그 시간을 모르므로
# 시간당 30회가 안전하다는 보장은 없다. 기본값 300초로 장시간 돌려본 뒤 조정한다(스펙 12장).
MIN_POLL_SECONDS = 120


@dataclass
class Config:
    x: int | None = None
    y: int | None = None
    # 위치를 저장할 때의 창 폭. 창 크기가 바뀌면 저장된 x를 보정하는 데 쓴다 —
    # 좌상단 좌표만 기억하면 창이 좁아졌을 때 오른쪽 구석에 붙여둔 창이
    # 화면 안쪽으로 밀려 들어온다.
    win_w: int | None = None
    poll_seconds: int = 300
    warn_pct: int = 70
    danger_pct: int = 90
    overlay_visible: bool = True


# 필드별 타입 표. Config에 필드를 추가하면 여기도 추가해야 한다 —
# 안 하면 그 설정이 조용히 무시되므로 테스트가 이 짝을 지킨다.
_TYPES = {
    "x": int,
    "y": int,
    "win_w": int,
    "poll_seconds": int,
    "warn_pct": int,
    "danger_pct": int,
    "overlay_visible": bool,
}


# 프로그램이 바꾸는 값은 이 셋뿐이다. 나머지(poll_seconds·warn_pct·danger_pct)는
# 사용자가 메모장으로 고치는 값이라 저장할 때 건드리지 않는다.
UI_OWNED = ("x", "y", "win_w", "overlay_visible")


def config_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "claude-usage-overlay" / "config.json"


def _coerce(raw: dict) -> dict:
    """읽을 수 없는 값은 조용히 버린다. 그 자리는 기본값이 채운다.

    이 파일은 트레이 메뉴 "설정 파일 열기"로 사용자가 메모장에서 직접 고친다.
    `{"poll_seconds": null}` 같은 오타 하나에 예외를 던지면 HUD가 아예 안 뜨고,
    pythonw에는 콘솔이 없어서 사용자는 원인을 볼 방법조차 없다.
    """
    clean: dict = {}
    for key, cast in _TYPES.items():
        value = raw.get(key)
        if value is None:
            continue
        if cast is bool:
            # bool("false")는 True다. 진짜 bool만 받는다.
            if isinstance(value, bool):
                clean[key] = value
            continue
        try:
            clean[key] = cast(value)
        except (TypeError, ValueError):
            continue
    return clean


def load_config(path: Path | None = None) -> Config:
    path = path or config_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raw = {}
    except (OSError, json.JSONDecodeError):
        raw = {}

    cfg = Config(**_coerce(raw))
    cfg.poll_seconds = max(MIN_POLL_SECONDS, cfg.poll_seconds)
    return cfg


def save_config(cfg: Config, path: Path | None = None) -> None:
    """디스크의 현재 내용 위에 UI가 소유한 값만 덮어쓴다.

    전체를 통째로 쓰면 안 된다. config는 기동 시 한 번만 읽으므로 우리가 들고
    있는 poll_seconds·warn_pct·danger_pct는 기동 시점에서 멈춰 있다. 사용자가
    "설정 파일 열기"로 그 값을 고친 뒤 오버레이를 한 번 드래그하기만 해도
    옛 값이 편집 위에 덮여 조용히 사라진다.

    파일이 아직 없으면(트레이 메뉴가 처음 만드는 경우) 전체를 쓴다.
    사용자가 고칠 키가 다 보여야 하기 때문이다.
    """
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raw = {}
    except (OSError, json.JSONDecodeError):
        raw = {}

    data = {**raw, **{k: getattr(cfg, k) for k in UI_OWNED}} if raw else asdict(cfg)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)
