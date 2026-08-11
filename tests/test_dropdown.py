"""드롭다운 판정. 창 없이 산수만 잰다."""

from claude_usage_overlay.config import MIN_POLL_SECONDS
from claude_usage_overlay.dropdown import POLL_CHOICES, label_for, nearest


def test_the_floor_is_the_first_choice():
    """2분 아래는 호출 한도에 걸린다. 드롭다운에 그 아래 항목을 두면 안 된다."""
    assert POLL_CHOICES[0][0] == MIN_POLL_SECONDS


def test_the_choices_are_sorted():
    """정렬돼 있지 않으면 펼친 목록이 뒤죽박죽으로 보인다."""
    values = [v for v, _label in POLL_CHOICES]
    assert values == sorted(values)


def test_an_exact_value_stays_put():
    for value, _label in POLL_CHOICES:
        assert nearest(value) == value


def test_a_hand_edited_value_snaps_to_the_closest_choice():
    """파일에 손으로 240초를 적어둔 경우다. 5분(300)이 2분(120)보다 가깝다.
    드롭다운으로 바꾼 이상 피할 수 없고, 닫으면 그 값이 저장된다 (스펙 4.1절)."""
    assert nearest(240) == 300


def test_a_tie_goes_to_the_longer_period():
    """210초는 120과 300에서 같은 거리다. 긴 쪽으로 붙인다 — 짧은 쪽을 고르면
    측정되지 않은 호출 한도에 더 가까워진다 (config.MIN_POLL_SECONDS 주석)."""
    assert nearest(210) == 300


def test_values_outside_the_list_are_pulled_to_the_ends():
    assert nearest(1) == 120
    assert nearest(86400) == 1800


def test_label_follows_the_value():
    assert label_for(300) == "5분"
    assert label_for(240) == "5분", "표시도 붙은 항목을 따라간다"
