"""이 프로그램의 판 번호. 여기가 유일한 원본이다.

`pyproject.toml`이 `[tool.setuptools.dynamic]`으로 이 값을 읽고, 트레이 메뉴가
이 값을 그리고, `build.py`가 exe 파일 속성에 박고, 릴리스 워크플로가 태그와
대조해 다르면 빌드 전에 멈춘다.

**`importlib.metadata`로 읽지 않는다.** 이 패키지는 `pip install`된 적이 없고
exe 안에도 패키지 메타데이터가 없어서, 그 방식은 소스 실행과 exe에서 서로 다르게
동작한다(한쪽은 값을 내고 한쪽은 `PackageNotFoundError`다). 파일에 박힌 문자열은
두 경우 모두 같은 값을 낸다.
"""

__version__ = "0.1.0"
