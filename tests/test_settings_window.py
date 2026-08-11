"""초안 → Config 커밋과 슬라이더 한계. 창을 띄우지 않는다.

**자동 실행과 아이콘 고정은 Config에 들어가지 않는다.** 진짜 상태가 레지스트리에
있으므로, 창을 열 때 거기서 읽어 체크박스를 그리고 닫을 때 거기에 쓴다.
그래서 초안에는 있고 커밋 결과에는 없다 (스펙 4.3절).
"""

from claude_usage_overlay.config import PCT_MAX, PCT_MIN, PCT_STEP, Config
from claude_usage_overlay.settings_window import (
    Draft,
    commit_draft,
    danger_bounds,
    draft_from,
    warn_bounds,
)


def test_the_draft_starts_from_the_live_config():
    cfg = Config(poll_seconds=600, warn_pct=65, danger_pct=85, overlay_visible=False)
    draft = draft_from(cfg, autostart_on=True, promote_on=False)
    assert draft.poll_seconds == 600
    assert (draft.warn_pct, draft.danger_pct) == (65, 85)
    assert draft.overlay_visible is False
    assert draft.autostart is True and draft.promote is False


def test_commit_moves_every_config_field():
    cfg = Config()
    commit_draft(
        Draft(
            overlay_visible=False, overlay_detailed=True, poll_seconds=1800,
            warn_pct=55, danger_pct=95, autostart=True, promote=True,
        ),
        cfg,
    )
    assert (cfg.overlay_visible, cfg.overlay_detailed) == (False, True)
    assert cfg.poll_seconds == 1800
    assert (cfg.warn_pct, cfg.danger_pct) == (55, 95)


def test_commit_does_not_invent_config_fields_for_the_registry_values():
    """autostart·promote가 Config에 새면 파일과 레지스트리가 두 진실이 된다."""
    cfg = Config()
    commit_draft(draft_from(cfg, autostart_on=True, promote_on=True), cfg)
    assert not hasattr(cfg, "autostart")
    assert not hasattr(cfg, "promote")


def test_a_committed_config_survives_a_reload_unchanged(tmp_path):
    """설정창이 쓴 값이 load_config의 보정에 걸리면 닫자마자 값이 바뀐다."""
    from claude_usage_overlay.config import load_config, save_config

    cfg = Config()
    commit_draft(
        Draft(True, False, 1800, PCT_MAX - PCT_STEP, PCT_MAX, False, False), cfg
    )
    path = tmp_path / "config.json"
    save_config(cfg, path)
    after = load_config(path)
    assert (after.warn_pct, after.danger_pct) == (PCT_MAX - PCT_STEP, PCT_MAX)
    assert after.poll_seconds == 1800


def test_a_hand_edited_period_is_committed_as_the_snapped_value():
    """파일에 240초가 적혀 있으면 드롭다운은 5분을 보여준다. 사용자가 그것을
    건드리지 않아도 **닫을 때 300이 저장돼야 한다** — 240이 남으면 화면과 파일이
    갈라지고 다음에 열 때 또 같은 일이 벌어진다 (스펙 4.1절).

    설정창은 위젯을 만든 직후 초안을 위젯이 고른 값으로 맞춘다. 여기서는 그
    맞추기를 nearest()로 재현해 규칙 자체를 잰다.
    """
    from claude_usage_overlay.dropdown import nearest

    cfg = Config(poll_seconds=240)
    draft = draft_from(cfg, autostart_on=False, promote_on=False)
    draft.poll_seconds = nearest(draft.poll_seconds)
    commit_draft(draft, cfg)
    assert cfg.poll_seconds == 300


def test_the_two_sliders_never_overlap():
    """노란은 빨간보다 5%p 아래에서 멈추고 반대도 같다. **서로 밀어내지 않고
    그 자리에 선다** — 밀어내면 한쪽을 끌 때 다른 쪽이 따라와 값이 둘 다 바뀐다."""
    lo, hi = warn_bounds()
    assert (lo, hi) == (PCT_MIN, PCT_MAX - PCT_STEP)
    lo, hi = danger_bounds()
    assert (lo, hi) == (PCT_MIN + PCT_STEP, PCT_MAX)


def test_the_bounds_leave_room_for_the_gap():
    """빨간의 하한이 노란의 하한보다 정확히 한 칸 위여야, 노란을 끝까지 올려도
    빨간이 갈 자리가 남는다."""
    assert danger_bounds()[0] - warn_bounds()[0] == PCT_STEP
    assert danger_bounds()[1] - warn_bounds()[1] == PCT_STEP
