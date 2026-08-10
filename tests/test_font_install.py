"""글꼴 설치의 판정 부분을 네트워크·레지스트리 없이 검증한다.

실제 다운로드와 레지스트리 쓰기는 얇은 껍데기이고, 틀리기 쉬운 것은
"어느 zip을 받을지"와 "그 안에서 무엇을 꺼낼지"다.
"""

import io
import json
import zipfile

import pytest

from claude_usage_overlay import font_install
from claude_usage_overlay.font_install import (
    WANTED_FILES,
    extract_to,
    fetch_zip,
    is_installed,
    pick_zip_asset,
    registry_value_name,
    wanted_members,
)
from claude_usage_overlay.http_client import HttpResponse

# 2026-08-10 실제 릴리스 응답의 자산 목록 그대로.
ASSETS = [
    {"name": "Pretendard-1.3.9.zip", "browser_download_url": "https://x/Pretendard-1.3.9.zip"},
    {"name": "PretendardGOV-1.3.9.zip", "browser_download_url": "https://x/gov.zip"},
    {"name": "PretendardJP-1.3.9.zip", "browser_download_url": "https://x/jp.zip"},
    {"name": "PretendardStd-1.3.9.zip", "browser_download_url": "https://x/std.zip"},
]

# zip 내부 경로도 실물에서 가져왔다.
MEMBERS = [
    "public/variable/PretendardVariable.ttf",
    "public/static/Pretendard-Regular.otf",
    "public/static/Pretendard-Bold.otf",
    "public/static/alternative/Pretendard-Regular.ttf",
    "public/static/alternative/Pretendard-Bold.ttf",
    "public/static/alternative/Pretendard-Thin.ttf",
    "public/web/static/woff2/Pretendard-Regular.woff2",
]


def test_picks_the_plain_zip_not_the_variants():
    """GOV·JP·Std가 같은 릴리스에 함께 올라온다. 이름만 보고 가려야 한다."""
    assert pick_zip_asset(ASSETS) == "https://x/Pretendard-1.3.9.zip"


def test_variant_only_release_is_an_error_not_a_wrong_pick():
    """엉뚱한 zip을 받느니 실패하는 편이 낫다. 조용히 다른 글꼴을 깔면 안 된다."""
    with pytest.raises(LookupError):
        pick_zip_asset([a for a in ASSETS if not a["name"].startswith("Pretendard-")])


def test_picks_static_ttf_not_otf_or_variable():
    found = wanted_members(MEMBERS)
    assert set(found) == set(WANTED_FILES)
    assert found["Pretendard-Regular.ttf"].endswith("alternative/Pretendard-Regular.ttf")
    assert all(not p.endswith(".otf") for p in found.values())
    assert all("variable" not in p.lower() for p in found.values())


def test_unwanted_weights_are_left_out():
    """40여 개가 들어 있는 zip이다. 필요한 둘만 꺼낸다."""
    assert "Pretendard-Thin.ttf" not in wanted_members(MEMBERS)


def test_registry_value_name_matches_the_windows_convention():
    assert registry_value_name("Pretendard-Regular.ttf") == "Pretendard Regular (TrueType)"
    assert registry_value_name("Pretendard-Bold.ttf") == "Pretendard Bold (TrueType)"


def _fake_zip(names) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in names:
            archive.writestr(name, b"ttf-bytes-" + name.encode())
    return buffer.getvalue()


def test_extract_writes_only_the_wanted_files(tmp_path):
    written = extract_to(_fake_zip(MEMBERS), tmp_path)
    assert {p.name for p in written} == set(WANTED_FILES)
    assert {p.name for p in tmp_path.iterdir()} == set(WANTED_FILES)


def test_extract_leaves_no_partial_files_behind(tmp_path):
    """쓰는 중인 파일을 GDI가 읽으면 깨진 글꼴로 등록된다."""
    extract_to(_fake_zip(MEMBERS), tmp_path)
    assert not list(tmp_path.glob("*.part"))


def test_extract_fails_loudly_when_the_layout_changed(tmp_path):
    """판올림에서 경로가 바뀌면 빈손으로 성공했다고 하면 안 된다."""
    with pytest.raises(LookupError):
        extract_to(_fake_zip(["public/web/Pretendard-Regular.woff2"]), tmp_path)


def test_is_installed_requires_every_file(tmp_path):
    assert not is_installed(tmp_path)
    (tmp_path / WANTED_FILES[0]).write_bytes(b"x")
    assert not is_installed(tmp_path), "하나만 있으면 설치된 것이 아니다"
    (tmp_path / WANTED_FILES[1]).write_bytes(b"x")
    assert is_installed(tmp_path)


def test_install_is_a_no_op_when_already_present(tmp_path):
    """트레이 메뉴를 두 번 눌러도 47MB를 다시 받지 않는다."""
    for name in WANTED_FILES:
        (tmp_path / name).write_bytes(b"x")

    def explode(*a, **k):
        raise AssertionError("이미 설치돼 있으면 네트워크를 쓰면 안 된다")

    font_install.install(request_fn=explode, fonts_dir=tmp_path)


def test_fetch_zip_asks_github_then_downloads():
    calls = []

    def fake(method, url, headers, json_body=None, timeout=10.0):
        calls.append((url, headers.get("User-Agent"), timeout))
        if "api.github.com" in url:
            return HttpResponse(200, json.dumps({"assets": ASSETS}).encode(), {})
        return HttpResponse(200, b"zip-bytes", {})

    assert fetch_zip(request_fn=fake) == b"zip-bytes"
    assert calls[0][0] == font_install.RELEASE_API
    assert calls[1][0] == "https://x/Pretendard-1.3.9.zip"
    assert all(ua for _url, ua, _t in calls), "GitHub API는 User-Agent를 요구한다"
    assert calls[1][2] >= 60, "47MB에 기본 10초 제한은 짧다"


def test_fetch_zip_reports_a_failed_release_lookup():
    with pytest.raises(OSError):
        fetch_zip(request_fn=lambda *a, **k: HttpResponse(503, b"", {}))
