import sys

from claude_usage_overlay import autostart


def test_command_runs_the_package_with_pythonw(monkeypatch):
    monkeypatch.setattr(sys, "executable", r"C:\Python312\python.exe")
    cmd = autostart.build_command()
    # 콘솔 창이 뜨지 않도록 pythonw를 쓴다
    assert "pythonw.exe" in cmd
    assert "claude_usage_overlay" in cmd
    assert cmd.startswith('"')          # 공백 있는 경로를 위해 따옴표로 감싼다


def test_command_carries_the_package_path(monkeypatch):
    """시작 프로그램은 cwd가 저장소가 아니고 패키지는 설치돼 있지 않다.

    경로가 명령에 들어 있지 않으면 ModuleNotFoundError로 조용히 죽는다 —
    pythonw에는 콘솔이 없어서 그 오류를 볼 방법도 없다.
    """
    monkeypatch.setattr(sys, "executable", r"C:\Python312\python.exe")
    assert autostart.package_root().as_posix() in autostart.build_command()


def test_command_has_no_nested_double_quotes(monkeypatch):
    """레지스트리 값은 CommandLineToArgvW가 쪼갠다.

    큰따옴표는 exe를 감싸는 둘과 -c 인자를 감싸는 둘, 정확히 넷이어야 한다.
    파이썬 문자열에 큰따옴표를 쓰면 여기서 깨진다.
    """
    monkeypatch.setattr(sys, "executable", r"C:\Python312\python.exe")
    assert autostart.build_command().count('"') == 4


def test_command_handles_already_pythonw(monkeypatch):
    monkeypatch.setattr(sys, "executable", r"C:\Python312\pythonw.exe")
    assert autostart.build_command().count("pythonw.exe") == 1


def test_frozen_exe_registers_itself_directly(monkeypatch):
    """exe로 묶이면 sys.executable이 우리 exe다.

    거기에 `-c "..."`를 붙이면 그 문자열이 파이썬 코드가 아니라 앱의 argv로
    넘어가고, 자동 실행은 조용히 엉뚱하게 동작한다. exe 경로 하나면 된다.
    """
    monkeypatch.setattr(sys, "executable", r"D:\Apps\ClaudeUsageOverlay.exe")
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    cmd = autostart.build_command()
    assert cmd == r'"D:\Apps\ClaudeUsageOverlay.exe"'
    assert " -c " not in cmd
    assert "runpy" not in cmd


def test_source_run_still_uses_python(monkeypatch):
    """소스로 돌릴 때는 예전 그대로여야 한다."""
    monkeypatch.setattr(sys, "executable", r"C:\Python312\python.exe")
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert "runpy" in autostart.build_command()


def test_registry_constants_target_current_user():
    assert autostart.RUN_KEY == r"Software\Microsoft\Windows\CurrentVersion\Run"
    assert autostart.VALUE_NAME == "ClaudeUsageOverlay"
