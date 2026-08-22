"""빌드 스크립트의 순수 함수.

`import build`는 최상위 `build.py`로 간다. 같은 이름의 `build/` 디렉터리가
옆에 있지만 그건 `__init__.py`가 없는 디렉터리라, 실제 모듈이 이긴다(실측).
"""

import io

import build


def test_version_tuple_pads_to_four_slots():
    """VS_VERSION_INFO의 filevers는 네 칸이다. "0.1.0"은 세 칸이라
    그대로 넘기면 PyInstaller가 구조체를 못 채운다."""
    assert build.version_tuple("0.1.0") == (0, 1, 0, 0)


def test_version_tuple_keeps_multi_digit_parts():
    """0.9 다음이 0.10이다. 문자열을 자리마다 자르는 구현이면 여기서 깨진다."""
    assert build.version_tuple("1.12.3") == (1, 12, 3, 0)


def test_utf8_output_switches_a_cp1252_stream():
    """GitHub Actions의 windows 러너가 cp1252다. 바꾸지 않으면 이 스크립트가
    내는 한국어 문구가 거기서 UnicodeEncodeError로 빌드를 죽인다."""
    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    build.use_utf8_output(stream)

    assert stream.encoding.lower() == "utf-8"
    stream.write("아이콘: 완료")  # cp1252였다면 여기서 터진다


def test_utf8_output_ignores_streams_that_cannot_switch():
    """pythonw로 돌리면 sys.stdout이 None이다. 출력 설정 때문에 빌드가 죽는
    것은 본말이 뒤집힌 것이라, 못 바꾸는 스트림은 그냥 넘긴다."""
    build.use_utf8_output(None, object())
