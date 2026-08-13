import json

from claude_usage_overlay import config
from claude_usage_overlay.config import Config, load_config, save_config


def test_missing_file_returns_defaults(tmp_path):
    cfg = load_config(tmp_path / "none.json")
    assert cfg.poll_seconds == 300
    assert cfg.warn_pct == 70
    assert cfg.danger_pct == 90
    assert cfg.overlay_visible is True


def test_broken_json_returns_defaults(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{ this is not json", encoding="utf-8")
    assert load_config(p).poll_seconds == 300


def test_partial_file_fills_missing_with_defaults(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"poll_seconds": 600}), encoding="utf-8")
    cfg = load_config(p)
    assert cfg.poll_seconds == 600
    assert cfg.warn_pct == 70
    assert cfg.danger_pct == 90


def test_save_then_load_roundtrip(tmp_path):
    p = tmp_path / "nested" / "config.json"
    save_config(Config(poll_seconds=600, overlay_visible=False), p)
    cfg = load_config(p)
    assert (cfg.poll_seconds, cfg.overlay_visible) == (600, False)


def test_poll_seconds_floor_is_enforced(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"poll_seconds": 5}), encoding="utf-8")
    # 엔드포인트 한도가 측정되지 않았으므로 너무 짧은 값은 120초로 올린다
    assert load_config(p).poll_seconds == 120


def test_wrong_types_fall_back_to_defaults(tmp_path):
    """사용자가 메모장으로 직접 고치는 파일이다. 오타 하나로 HUD가 안 뜨면 안 된다.

    pythonw에는 콘솔이 없어서 여기서 예외가 나면 원인조차 화면에 남지 않는다.
    """
    p = tmp_path / "config.json"
    for broken in ({"poll_seconds": None}, {"poll_seconds": "오분"}, {"warn_pct": "칠십"}):
        p.write_text(json.dumps(broken), encoding="utf-8")
        cfg = load_config(p)
        assert cfg.poll_seconds == 300
        assert cfg.warn_pct == 70


def test_a_broken_value_does_not_discard_the_good_ones(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"poll_seconds": 600, "warn_pct": "칠십"}), encoding="utf-8")
    cfg = load_config(p)
    assert cfg.poll_seconds == 600
    assert cfg.warn_pct == 70


def test_overlay_visible_only_accepts_a_real_bool(tmp_path):
    """bool("false")는 True다. 문자열을 받아주면 설정이 거꾸로 동작한다."""
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"overlay_visible": "false"}), encoding="utf-8")
    assert load_config(p).overlay_visible is True   # 버리고 기본값

    p.write_text(json.dumps({"overlay_visible": False}), encoding="utf-8")
    assert load_config(p).overlay_visible is False


def test_every_config_field_has_a_coercion_rule():
    """Config에 필드를 추가하고 _TYPES를 안 고치면 그 설정이 조용히 무시된다."""
    assert set(Config.__dataclass_fields__) == set(config._TYPES)


def test_overlay_detailed_defaults_to_the_basic_mode(tmp_path):
    """기본값이 false인 쪽이 기본 모드와 일치해서 파일을 열어본 사람이
    헷갈리지 않는다 (스펙 9장)."""
    assert load_config(tmp_path / "none.json").overlay_detailed is False


def test_overlay_detailed_only_accepts_a_real_bool(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"overlay_detailed": "true"}), encoding="utf-8")
    assert load_config(p).overlay_detailed is False   # 버리고 기본값

    p.write_text(json.dumps({"overlay_detailed": True}), encoding="utf-8")
    assert load_config(p).overlay_detailed is True


def test_save_writes_the_whole_file(tmp_path):
    """이제 전부 GUI가 소유한다. 부분 병합이 없어졌으므로 디스크의 옛 키가
    남아 있으면 안 된다 — 남으면 다음 판올림에서 사라진 필드가 되살아난다."""
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"poll_seconds": 900, "옛날키": 1}), encoding="utf-8")
    save_config(Config(poll_seconds=600), p)
    written = json.loads(p.read_text(encoding="utf-8"))
    assert set(written) == set(Config.__dataclass_fields__)
    assert written["poll_seconds"] == 600


def test_ui_owned_is_gone():
    """부분 병합의 근거였던 '나머지는 메모장으로 고치는 값'이 사라졌다.
    상수가 남아 있으면 다음 사람이 그 규칙이 아직 산다고 읽는다."""
    assert not hasattr(config, "UI_OWNED")


def test_warn_above_danger_is_corrected_on_load(tmp_path):
    """warn ≥ danger면 노란색이 영영 안 나온다. 설정창에서만 고치면 창을 한 번도
    안 연 사람은 그대로 남으므로 불러올 때 바로잡는다 (스펙 4.1절)."""
    p = tmp_path / "config.json"
    for warn, danger in ((95, 90), (90, 90), (100, 60)):
        p.write_text(json.dumps({"warn_pct": warn, "danger_pct": danger}), encoding="utf-8")
        cfg = load_config(p)
        assert cfg.danger_pct == danger, "danger를 기준으로 두고 warn을 내린다"
        assert cfg.warn_pct == danger - config.PCT_STEP


def test_the_correction_never_pushes_warn_below_zero(tmp_path):
    """손으로 danger=2를 적어둔 경우다. 음수 임계값을 만들면 안 된다."""
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"warn_pct": 50, "danger_pct": 2}), encoding="utf-8")
    assert load_config(p).warn_pct == 0


def test_a_sane_pair_is_left_alone(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"warn_pct": 60, "danger_pct": 80}), encoding="utf-8")
    cfg = load_config(p)
    assert (cfg.warn_pct, cfg.danger_pct) == (60, 80)


def test_the_slider_gap_is_the_slider_step():
    """5단위 스냅과 5%p 간격이 같은 값이어야 슬라이더가 자기 한계에 정확히 선다.
    두 상수로 갈라두면 한쪽만 고쳐졌을 때 손잡이가 한 칸 못 가거나 넘어간다."""
    assert config.PCT_STEP == 5
    assert config.PCT_MIN < config.PCT_MAX


def test_first_save_writes_every_field(tmp_path):
    """트레이 메뉴가 파일을 처음 만들 때는 고칠 키가 다 보여야 한다."""
    p = tmp_path / "config.json"
    save_config(Config(poll_seconds=600), p)
    assert set(json.loads(p.read_text(encoding="utf-8"))) == set(Config.__dataclass_fields__)


def test_save_survives_a_broken_file_on_disk(tmp_path):
    """읽어서 병합하는 코드가 깨진 파일에서 예외를 던지면 안 된다."""
    p = tmp_path / "config.json"
    p.write_text("{ not json", encoding="utf-8")
    save_config(Config(overlay_visible=False), p)
    assert load_config(p).overlay_visible is False
