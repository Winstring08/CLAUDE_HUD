"""번들 글꼴이 자리에 있고, 없어도 조용히 넘어가는지 본다.

**다운로드·압축 해제 판정은 사라졌다.** 글꼴이 exe 안에 있으므로 받을 것도
고를 것도 없다. 남은 위험은 "번들이 빠진 채로 빌드됐다"와 "경로를 잘못 봤다"
둘이고, 둘 다 조용히 실패하면 화면이 Segoe UI로 떨어질 뿐이라 아무도 못 본다.
그래서 여기서 잡는다.
"""

from pathlib import Path

from claude_usage_overlay import font_install
from claude_usage_overlay.font_install import BUNDLE_FILES, bundle_dir, font_file_for


def test_bundle_files_are_actually_in_the_repo():
    """빠진 채로 빌드되면 화면이 조용히 Segoe UI로 떨어진다."""
    for name in BUNDLE_FILES:
        path = bundle_dir() / name
        assert path.exists(), f"{path}가 없다 — 플랜 Task 1 Step 1을 보라"
        assert path.stat().st_size > 1_000_000, f"{path}가 너무 작다"


def test_the_license_ships_with_the_fonts():
    """SIL OFL 1.1은 라이선스 파일 동봉을 조건으로 번들을 허용한다."""
    text = (bundle_dir() / "OFL.txt").read_text(encoding="utf-8", errors="replace")
    assert "SIL OPEN FONT LICENSE" in text.upper()


def test_bundle_dir_prefers_the_pyinstaller_temp_dir(monkeypatch):
    """단일 파일 exe는 자기 자신을 임시 폴더에 풀고 그 안에서 돈다.
    sys._MEIPASS를 안 보면 exe에서 글꼴을 못 찾는다."""
    import sys

    monkeypatch.setattr(sys, "_MEIPASS", r"C:\Temp\_MEI123", raising=False)
    assert bundle_dir() == Path(r"C:\Temp\_MEI123") / "claude_usage_overlay" / "fonts"


def test_bundle_dir_falls_back_to_the_package_folder(monkeypatch):
    import sys

    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    assert bundle_dir().name == "fonts"
    assert bundle_dir().parent.name == "claude_usage_overlay"


def test_activate_is_quiet_when_nothing_is_there(tmp_path):
    """기동할 때마다 부르는 함수다. 글꼴이 없어도 조용히 0을 돌려줘야 한다."""
    assert font_install.activate(tmp_path) == 0


def test_activate_survives_a_broken_font_file(tmp_path):
    """받다 만 파일이 남아 있어도 여기서 죽으면 HUD가 아예 안 뜬다."""
    (tmp_path / BUNDLE_FILES[0]).write_bytes(b"this is not a font")
    assert font_install.activate(tmp_path) == 0


def test_activate_loads_the_bundle():
    """번들을 실제로 GDI에 올린다. 두 번 올려도 무해하다 (참조 계수)."""
    assert font_install.activate() == len(BUNDLE_FILES)


def test_font_file_for_resolves_the_two_families_we_draw_with():
    """잉크 상자를 재려면 Tk 패밀리 이름이 아니라 파일 경로가 필요하다."""
    assert font_file_for("Pretendard", bold=True).name == "Pretendard-Bold.ttf"
    assert font_file_for("Pretendard", bold=False).name == "Pretendard-Regular.ttf"
    assert font_file_for("Segoe UI", bold=True).name == "segoeuib.ttf"


def test_font_file_for_gives_up_on_an_unknown_family():
    """모르는 글꼴이면 None이다. 그때 오버레이는 잉크 정렬을 포기하고
    레이아웃 상자 중앙에 놓는다 — 1px 어긋날 뿐 화면은 정상이다."""
    assert font_file_for("이런글꼴은없다") is None
