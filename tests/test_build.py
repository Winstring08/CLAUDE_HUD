"""빌드 스크립트의 순수 함수.

`import build`는 최상위 `build.py`로 간다. 같은 이름의 `build/` 디렉터리가
옆에 있지만 그건 `__init__.py`가 없는 디렉터리라, 실제 모듈이 이긴다(실측).
"""

import build


def test_version_tuple_pads_to_four_slots():
    """VS_VERSION_INFO의 filevers는 네 칸이다. "0.1.0"은 세 칸이라
    그대로 넘기면 PyInstaller가 구조체를 못 채운다."""
    assert build.version_tuple("0.1.0") == (0, 1, 0, 0)


def test_version_tuple_keeps_multi_digit_parts():
    """0.9 다음이 0.10이다. 문자열을 자리마다 자르는 구현이면 여기서 깨진다."""
    assert build.version_tuple("1.12.3") == (1, 12, 3, 0)
