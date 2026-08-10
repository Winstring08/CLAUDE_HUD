import json

from claude_usage_overlay import config
from claude_usage_overlay.config import Config, load_config, save_config


def test_missing_file_returns_defaults(tmp_path):
    cfg = load_config(tmp_path / "none.json")
    assert cfg.poll_seconds == 300
    assert cfg.warn_pct == 70
    assert cfg.danger_pct == 90
    assert cfg.overlay_visible is True
    assert cfg.x is None and cfg.y is None


def test_broken_json_returns_defaults(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{ this is not json", encoding="utf-8")
    assert load_config(p).poll_seconds == 300


def test_partial_file_fills_missing_with_defaults(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"x": 100, "y": 200}), encoding="utf-8")
    cfg = load_config(p)
    assert cfg.x == 100
    assert cfg.y == 200
    assert cfg.warn_pct == 70


def test_save_then_load_roundtrip(tmp_path):
    p = tmp_path / "nested" / "config.json"
    save_config(Config(x=12, y=34, poll_seconds=600), p)
    cfg = load_config(p)
    assert (cfg.x, cfg.y, cfg.poll_seconds) == (12, 34, 600)


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
    for broken in ({"poll_seconds": None}, {"poll_seconds": "오분"}, {"x": "왼쪽"}):
        p.write_text(json.dumps(broken), encoding="utf-8")
        cfg = load_config(p)
        assert cfg.poll_seconds == 300
        assert cfg.x is None


def test_a_broken_value_does_not_discard_the_good_ones(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"x": 100, "y": "아래"}), encoding="utf-8")
    cfg = load_config(p)
    assert cfg.x == 100
    assert cfg.y is None


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


def test_manual_edits_survive_a_position_save(tmp_path):
    """config는 기동 시 한 번만 읽는다. 저장할 때 전체를 쓰면 오버레이를 한 번
    드래그하는 것만으로 사용자의 편집이 기동 시점 값으로 덮여 조용히 사라진다.

    "설정 파일 열기"가 트레이 메뉴에 있는 이상 직접 편집은 지원 경로다.
    """
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"poll_seconds": 900}), encoding="utf-8")
    cfg = load_config(p)                                            # 기동
    p.write_text(json.dumps({"poll_seconds": 1200, "warn_pct": 50}), encoding="utf-8")
    cfg.x, cfg.y = 100, 200                                         # 드래그
    save_config(cfg, p)

    after = load_config(p)
    assert after.poll_seconds == 1200
    assert after.warn_pct == 50
    assert (after.x, after.y) == (100, 200)


def test_first_save_writes_every_field(tmp_path):
    """트레이 메뉴가 파일을 처음 만들 때는 고칠 키가 다 보여야 한다."""
    p = tmp_path / "config.json"
    save_config(Config(poll_seconds=600), p)
    assert set(json.loads(p.read_text(encoding="utf-8"))) == set(Config.__dataclass_fields__)


def test_save_survives_a_broken_file_on_disk(tmp_path):
    """읽어서 병합하는 코드가 깨진 파일에서 예외를 던지면 안 된다."""
    p = tmp_path / "config.json"
    p.write_text("{ not json", encoding="utf-8")
    save_config(Config(x=1, y=2), p)
    assert load_config(p).x == 1
