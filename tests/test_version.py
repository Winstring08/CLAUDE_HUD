"""버전이 한 군데에만 있는지 지킨다.

두 군데 있으면 반드시 어긋난다 — 어긋난 사실은 릴리스가 나간 뒤 받은 사람
쪽에서만 드러난다.
"""

import re
import tomllib
from pathlib import Path

from claude_usage_overlay.version import __version__

ROOT = Path(__file__).resolve().parent.parent


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_version_is_semver():
    """릴리스 워크플로가 태그에서 `v`만 떼어 이 값과 문자열 비교한다.
    `0.1.0-beta` 같은 값은 태그 이름과 맞추기 어려워 쓰지 않는다."""
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__), __version__


def test_pyproject_has_no_version_of_its_own():
    """pyproject가 자기 값을 들고 있으면 그게 두 번째 원본이 된다."""
    project = _pyproject()["project"]
    assert "version" not in project
    assert "version" in project["dynamic"]


def test_pyproject_points_at_version_py():
    attr = _pyproject()["tool"]["setuptools"]["dynamic"]["version"]["attr"]
    assert attr == "claude_usage_overlay.version.__version__"
