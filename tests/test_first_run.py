"""첫 실행 판정.

**안내창 테스트는 사라졌다.** 그 창을 없앴기 때문이다 — 사용자가 아이콘을 직접
꺼낼 필요가 없다는 것이 확인되어 알릴 것이 없어졌다 (first_run 머리말).

남은 판정 하나가 지키는 것은 "자동 고정이 첫 실행에 딱 한 번만 돈다"이다.
여기가 틀리면 매 기동마다 켜져서, 나중에 직접 숨긴 사람과 싸운다.
"""

from claude_usage_overlay import first_run
from claude_usage_overlay.first_run import is_first_run


def test_a_missing_config_is_a_first_run(tmp_path):
    assert is_first_run(tmp_path / "config.json") is True


def test_an_existing_config_is_not(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{}", encoding="utf-8")
    assert is_first_run(path) is False


def test_a_broken_config_is_not_a_first_run(tmp_path):
    """깨진 파일도 '한 번 켠 적이 있다'는 증거다. 내용을 읽어 판정하면 오타
    하나에 자동 고정이 매 기동마다 되살아난다."""
    path = tmp_path / "config.json"
    path.write_text("{ not json", encoding="utf-8")
    assert is_first_run(path) is False


def test_the_intro_window_is_gone():
    """없앤 것이 되살아나면 안내창이 다시 뜬다. 문구도 함께 사라져야 한다 —
    '다음 로그온부터'라는 거짓 약속이 그 안에 있었다."""
    for name in ("show_intro", "last_line", "LAST_LINE_WIN11", "LAST_LINE_WIN10"):
        assert not hasattr(first_run, name), name
