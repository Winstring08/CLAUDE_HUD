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

# 사용률 임계값의 단위. 설정창 슬라이더가 이 값으로 스냅하고, 노란·빨간이
# 서로에게서 이만큼 떨어져 선다. **두 용도가 같은 상수여야 한다** — 갈라두면
# 한쪽만 고쳐졌을 때 손잡이가 자기 한계에 정확히 서지 못한다.
PCT_STEP = 5
PCT_MIN, PCT_MAX = 50, 100


@dataclass
class Config:
    # 창 위치는 저장하지 않는다. 드래그해서 옮긴 자리는 그 세션에서만 유지되고,
    # 다시 켜면 늘 같은 자리(화면 오른쪽 위)에 뜬다 — 어디 있을지 늘 알 수 있는
    # 편이 낫고, 저장된 좌표가 지금 없는 모니터를 가리키는 사고도 사라진다.
    poll_seconds: int = 300
    warn_pct: int = 70
    danger_pct: int = 90
    overlay_visible: bool = True
    # 기본값 false가 기본 모드(66×66)와 일치한다. 파일을 열어본 사람이
    # true를 기본으로 보면 지금 보이는 창과 어긋나 헷갈린다.
    overlay_detailed: bool = False


# 필드별 타입 표. Config에 필드를 추가하면 여기도 추가해야 한다 —
# 안 하면 그 설정이 조용히 무시되므로 테스트가 이 짝을 지킨다.
_TYPES = {
    "poll_seconds": int,
    "warn_pct": int,
    "danger_pct": int,
    "overlay_visible": bool,
    "overlay_detailed": bool,
}


def config_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "claude-usage-overlay" / "config.json"


def _coerce(raw: dict) -> dict:
    """읽을 수 없는 값은 조용히 버린다. 그 자리는 기본값이 채운다.

    옛 버전이 남긴 파일이나 손으로 고친 파일이 들어올 수 있다.
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
    # warn ≥ danger면 노란색이 영영 안 나온다. 설정창에서만 보정하면 창을 한 번도
    # 안 연 사람은 그대로 남으므로, poll_seconds의 하한을 거는 것과 같은 자리에서
    # 바로잡는다 (스펙 4.1절).
    #
    # **danger를 기준으로 두고 warn을 내린다.** 둘 중 결과가 무거운 쪽이 danger라
    # 그쪽을 사용자 뜻으로 존중한다. 음수까지 내려가지는 않게 0에서 멈춘다.
    if cfg.warn_pct >= cfg.danger_pct:
        cfg.warn_pct = max(0, cfg.danger_pct - PCT_STEP)
    return cfg


def save_config(cfg: Config, path: Path | None = None) -> None:
    """전체를 쓴다.

    예전에는 디스크 내용 위에 UI가 소유한 값만 덮었다. 근거는 "나머지는 사용자가
    메모장으로 고치는 값"이었는데, 이제 전부 설정창이 소유하므로 그 근거가
    사라졌다. 남는 위험은 프로그램이 켜진 채 파일을 손으로 고치는 경우뿐이고,
    이제 그럴 이유가 없다 — 트레이의 "설정 파일 열기"도 함께 사라졌다.

    임시 파일에 쓰고 바꿔치운다. 반쯤 쓰인 파일이 남으면 다음 기동에서
    전부 기본값으로 떨어진다.
    """
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")
    os.replace(tmp, path)
