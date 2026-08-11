"""첫 실행 판정과 안내 문구. 창을 띄우지 않는다."""

from claude_usage_overlay import first_run
from claude_usage_overlay.first_run import is_first_run, last_line


def test_a_missing_config_is_a_first_run(tmp_path):
    assert is_first_run(tmp_path / "config.json") is True


def test_an_existing_config_is_not(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{}", encoding="utf-8")
    assert is_first_run(path) is False


def test_a_broken_config_is_not_a_first_run(tmp_path):
    """깨진 파일도 '한 번 켠 적이 있다'는 증거다. 안내창을 다시 띄우면
    매 실행마다 뜬다."""
    path = tmp_path / "config.json"
    path.write_text("{ not json", encoding="utf-8")
    assert is_first_run(path) is False


def test_windows_eleven_promises_the_next_logon():
    """첫 실행에 IsPromoted=1을 써두므로 이 약속이 참이다."""
    assert last_line(supported=True) == first_run.LAST_LINE_WIN11
    assert "다음 로그온" in last_line(supported=True)


def test_windows_ten_points_at_its_own_settings_screen():
    """Win10에는 우리가 써둘 값이 없으므로 앞의 약속을 할 수 없다.
    대신 Win10에만 있는 아이콘별 설정 화면을 가리킨다 (스펙 2.3절)."""
    line = last_line(supported=False)
    assert line == first_run.LAST_LINE_WIN10
    assert "다음 로그온" not in line
    assert "작업 표시줄에 표시할 아이콘 선택" in line


def test_show_intro_saves_the_live_config_not_a_fresh_one(monkeypatch, root):
    """새 Config()를 저장하면 안내창이 뜨기 전에 오버레이가 이미 저장한 값을 덮는다.

    **이 테스트만 창을 만든다.** 검증하려는 것이 "창을 띄우는 경로가 어떤 객체를
    저장하는가"라서 그 경로를 실제로 지나야 한다. save_config를 가로채므로
    디스크에는 쓰지 않고, 만들어진 Toplevel은 끝나고 지운다 — 루트가 세션
    픽스처라 그냥 두면 남은 테스트 내내 화면에 떠 있게 된다.
    """
    from claude_usage_overlay.config import Config

    saved = []
    monkeypatch.setattr(first_run, "save_config", saved.append)

    cfg = Config(overlay_visible=False)
    before = set(root.winfo_children())
    try:
        first_run.show_intro(root, cfg, supported=True)
    finally:
        for child in set(root.winfo_children()) - before:
            child.destroy()

    assert saved == [cfg], "살아 있는 Config를 그대로 저장해야 한다"
    assert saved[0].overlay_visible is False
