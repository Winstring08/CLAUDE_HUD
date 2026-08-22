"""진입점의 배선 중 소스만 봐도 지킬 수 있는 것들.

main()을 실제로 부르면 창과 스레드가 뜨고 API를 부른다. 여기서 지키려는 것은
**순서와 존재**뿐이라 소스를 읽어 판정한다 — 무거운 하네스를 세우면 그 하네스가
판정하려는 축(창·스레드·파일)을 그대로 바꿔버린다.
"""

from pathlib import Path

from claude_usage_overlay import __main__ as entry

SOURCE = Path(entry.__file__).read_text(encoding="utf-8")


def test_the_first_run_check_comes_before_the_config_is_written():
    """순서가 뒤집히면 config.json이 먼저 생겨 first가 늘 False가 되고,
    첫 실행 자동 고정이 영영 돌지 않는다."""
    assert SOURCE.index("is_first_run()") < SOURCE.index("save_config(config)")


def test_the_first_run_marks_itself_so_it_only_happens_once():
    """예전에는 안내창이 이 저장을 겸했다. 그 창을 없앴으므로 진입점이 직접
    남겨야 한다 — 안 남기면 자동 고정이 매 기동마다 돌아, 나중에 직접 숨긴
    사람과 싸운다."""
    body = SOURCE[SOURCE.index("if first:"):]
    assert "save_config(config)" in body
    assert "promote_when_ready" in body


def test_the_intro_window_is_not_wired_anymore():
    assert "show_intro" not in SOURCE


def test_fonts_are_loaded_before_tk_starts():
    """Tk는 시작할 때 글꼴 목록을 읽는다. 나중에 올리면 이번 실행에서는 못 쓴다."""
    assert SOURCE.index("font_install.activate()") < SOURCE.index("tk.Tk()")


def test_dpi_awareness_comes_first():
    """이걸 빠뜨리면 Windows가 창을 비트맵 확대하고 그 위에 우리가 배율을 또
    곱해 창이 배율의 제곱만큼 커진다."""
    assert SOURCE.index("enable_dpi_awareness()") < SOURCE.index("tk.Tk()")
