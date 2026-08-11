"""기본 모드 · 갱신 지연 · 모드 전환 위치. 전부 창 없이 재는 순수 함수다."""

from datetime import datetime, timedelta, timezone

import pytest

from claude_usage_overlay import theme
from claude_usage_overlay import overlay as ov
from claude_usage_overlay.models import HudState, Status, UsageSnapshot

NOW = datetime(2026, 8, 11, 3, 0, tzinfo=timezone.utc)
POLL = 300


def _at(seconds):
    return NOW + timedelta(seconds=seconds)


def _state(status=Status.OK, pct=62.0, fetched=NOW, resets=None):
    return HudState(status, UsageSnapshot(pct, resets, None, fetched), "")


# --- 갱신 지연 임계 (스펙 3.1절) ---


def test_one_missed_tick_keeps_the_number():
    """poller._handle_transient()의 첫 백오프가 poll_seconds라 첫 실패 뒤 다음
    시도는 성공 시점 + 600초다. 그때까지 숫자가 남아 있어야 한다."""
    assert not ov.is_refresh_gap(NOW, _at(POLL), POLL)
    assert not ov.is_refresh_gap(NOW, _at(POLL * 2), POLL)


def test_two_missed_ticks_erase_the_number():
    """낡은 숫자는 없느니만 못하다. 한 주기를 통째로 건너뛰면 지운다."""
    assert ov.is_refresh_gap(NOW, _at(POLL * 2 + 61), POLL)


def test_the_boundary_is_two_periods_plus_a_minute():
    """60초는 분 반올림 경계에서 깜빡이지 않게 더한 것이다."""
    assert not ov.is_refresh_gap(NOW, _at(660), POLL)
    assert ov.is_refresh_gap(NOW, _at(661), POLL)


def test_a_single_auth_race_does_not_erase_anything():
    """_handle_unauthorized()는 백오프를 태우지 않아 다음 시도가 poll_seconds
    뒤다. 한 번의 401로 지우면 기본 5분 주기에서 4분 내내 빈 링이 된다."""
    assert not ov.is_refresh_gap(NOW, _at(POLL), POLL)


def test_the_threshold_follows_the_configured_period():
    """2분 주기로 줄여둔 사람에게 11분을 기다리게 하면 안 된다."""
    assert ov.is_refresh_gap(NOW, _at(361), 120)
    assert not ov.is_refresh_gap(NOW, _at(300), 120)


# --- 링 안에 그릴 것 (스펙 3.1절) ---


def test_relogin_is_a_loud_bang():
    """사용자가 조치해야 하는 것은 또렷하게."""
    assert ov.ring_symbol(HudState(Status.RELOGIN, None, "x"), NOW, POLL) == (
        "!", theme.RED,
    )


def test_a_schema_change_is_a_question_mark():
    assert ov.ring_symbol(HudState(Status.SCHEMA_ERROR, None, "x"), NOW, POLL) == (
        "?", theme.TEXT_LIGHT,
    )


def test_no_value_yet_is_an_ellipsis():
    """첫 조회 전이다. 여기서 `?`를 쓰면 켤 때마다 몇 초 동안 형식 변경 기호가 뜬다."""
    symbol, color = ov.ring_symbol(HudState(Status.STALE, None, "x"), NOW, POLL)
    assert (symbol, color) == (ov.RING_LOADING, theme.TEXT_DIM)


def test_a_refresh_gap_is_a_dim_bang():
    """`!`가 두 뜻을 갖지만 밝기로 갈린다 — 기다리면 낫는 것은 흐리게."""
    state = _state(Status.STALE, fetched=NOW)
    assert ov.ring_symbol(state, _at(661), POLL) == ("!", theme.TEXT_DIM_RING)


def test_a_fresh_value_draws_a_number_not_a_symbol():
    assert ov.ring_symbol(_state(), NOW, POLL) is None


def test_a_stale_but_recent_value_still_draws_the_number():
    """값이 낡았지만 아직 주기 안이면 통째로 흐리게만 그린다. 지우지 않는다."""
    assert ov.ring_symbol(_state(Status.STALE), _at(POLL), POLL) is None


def test_rate_limited_follows_the_same_rule_as_stale():
    """둘 다 '기다리면 낫는다'다. 429 벌칙이 길어지면 함께 지워져야 한다."""
    assert ov.ring_symbol(_state(Status.RATE_LIMITED), _at(POLL), POLL) is None
    assert ov.ring_symbol(_state(Status.RATE_LIMITED), _at(661), POLL) == (
        "!", theme.TEXT_DIM_RING,
    )


# --- 모드를 바꿀 때의 창 위치 (스펙 3.4절) ---

AREA = (0, 0, 1920, 1040)
SMALL, DETAIL = (66, 66), (190, 62)


def test_the_bottom_right_corner_stays_put():
    """기본 위치가 작업 영역 오른쪽 아래이므로 그래야 제자리에 남는다."""
    x, y = ov.resized_position(1830, 950, SMALL, DETAIL, AREA)
    assert (x + DETAIL[0], y + DETAIL[1]) == (1830 + 66, 950 + 66)


def test_shrinking_keeps_the_right_edge_too():
    x, y = ov.resized_position(1706, 916, DETAIL, SMALL, AREA)
    assert (x + SMALL[0], y + SMALL[1]) == (1706 + 190, 916 + 62)


def test_growing_at_the_left_edge_is_pushed_back_inside():
    """왼쪽 끝에 붙여둔 상태에서 자세히로 바꾸면 왼쪽으로 124px 자란다."""
    x, _y = ov.resized_position(0, 500, SMALL, DETAIL, AREA)
    assert x == 0


def test_the_window_never_hangs_off_the_bottom():
    x, y = ov.resized_position(100, 1030, SMALL, DETAIL, AREA)
    assert y + DETAIL[1] <= AREA[3]


def test_a_taskbar_on_top_is_respected():
    """작업 표시줄이 위에 있으면 작업 영역의 top이 0이 아니다."""
    area = (0, 48, 1920, 1080)
    _x, y = ov.resized_position(100, 50, SMALL, DETAIL, area)
    assert y >= 48


# --- 링 기하 (스펙 2.5절 · 3.1절) ---


def test_the_basic_ring_leaves_thirty_two_pixels_for_text():
    """바깥 지름 50 · 두께 5 → 안쪽 40. 링 선과 글자 사이 4px씩 남기면 32px."""
    assert ov.ring_text_limit(ov.SMALL_RING_BOX, ov.SMALL_RING_WIDTH, 1.0) == 32


def test_the_basic_ring_inner_box_is_forty_pixels():
    box = ov.ring_inner_box(ov.SMALL_RING_BOX, ov.SMALL_RING_WIDTH, 1.0)
    assert box == (13, 13, 53, 53)


def test_the_basic_window_is_a_square_with_an_eight_pixel_margin():
    assert ov.SMALL_RING_BOX == (8, 8, ov.SMALL_SIZE - 8, ov.SMALL_SIZE - 8)


# --- 드래그와 클릭 (스펙 3.3절) ---


def test_a_small_wobble_is_a_click():
    """단추를 누르는 동안 손이 1~2px 흔들리는 것은 정상이다."""
    assert not ov.is_drag(2, 0)
    assert not ov.is_drag(0, 2)
    assert not ov.is_drag(-2, 2)


def test_moving_past_the_threshold_is_a_drag():
    assert ov.is_drag(4, 0)
    assert ov.is_drag(0, -4)


def test_the_threshold_itself_counts_as_a_drag():
    assert ov.is_drag(3, 0)


def test_a_diagonal_wobble_is_judged_per_axis():
    """유클리드 거리로 재면 (3, 3)이 4.24가 되어 같은 3px 이동이 축에 따라
    갈린다. 축별 최댓값으로 본다."""
    assert ov.is_drag(3, 3)
    assert not ov.is_drag(2, 2)


@pytest.mark.parametrize("scale", (1.0, 1.25, 1.5))
def test_the_geometry_helpers_agree_at_every_scale(scale):
    """테스트가 코드와 **같은 산수**를 써야 한다. round(32 × 배율)로 어림하면
    125%에서 1px 어긋나 통과해야 할 것이 떨어지거나 반대가 된다."""
    box = ov.ring_inner_box(ov.SMALL_RING_BOX, ov.SMALL_RING_WIDTH, scale)
    limit = ov.ring_text_limit(ov.SMALL_RING_BOX, ov.SMALL_RING_WIDTH, scale)
    margin = round(ov.PCT_INNER_MARGIN * scale)
    assert (box[2] - box[0]) - 2 * margin == limit
