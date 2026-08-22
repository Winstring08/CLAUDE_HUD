# 배포 파이프라인 구현 플랜

> **에이전트에게:** 이 플랜이 완전한 작업 명세다. 한 번 읽고 끝까지 구현한다.
> 진행 표시는 체크박스(`- [ ]`)를 쓴다. **설계 문서를 함께 읽는다** — 이 플랜은
> 거기 적힌 근거 위에서 논증한다.

**목표:** `v0.1.0` 태그를 밀면 GitHub Actions가 Windows에서 빌드해 초안 릴리스에
`ClaudeUsageOverlay.exe`와 SHA-256을 붙이게 한다. 사람이 노트를 다듬고 게시하면
공개된다.

**아키텍처:** 프로그램 동작은 거의 그대로다. 버전 문자열의 원본을
`claude_usage_overlay/version.py` 하나로 모으고, `pyproject.toml`·트레이 메뉴·exe
파일 속성·CI의 태그 대조가 전부 그 값을 읽는다. 워크플로는 둘 —
`ci.yml`(테스트만)과 `release.yml`(태그 → 초안 릴리스)이고, 릴리스 쪽은 앞 단계가
깨지면 릴리스를 만들지 않는 순서가 곧 안전장치다.

**기술 스택:** Python 3.12, GitHub Actions(`windows-latest`), PyInstaller 6.22,
`gh` CLI(러너 기본 탑재), pytest

**스펙:** [`docs/specs/2026-08-23-release-pipeline-design.md`](../specs/2026-08-23-release-pipeline-design.md)

## 전역 제약

- Python 3.12 전용. `str | None` 등 3.10+ 문법을 쓴다.
- **Windows 전용.** macOS/Linux 빌드는 범위 밖이다.
- **런타임 외부 의존성은 `pystray`와 `pillow` 둘뿐이다.** 새 런타임 의존성을
  추가하지 않는다. PyInstaller·pytest는 개발·빌드 전용이다.
- 사용자에게 보이는 모든 문구는 한국어로 쓴다. 워크플로의 step 이름도 한국어다.
- **exe 이름은 `ClaudeUsageOverlay.exe`다.** 바꾸지 않는다 — 받은 사람의 바로가기와
  자동 실행 레지스트리 값이 이 경로를 가리킨다 (스펙 2장).
- **버전 태그는 `v` 접두 + SemVer다** (`v0.1.0`). 한 번 민 태그는 재사용하지 않는다.
- **저작권자는 `권승현`, 라이선스는 MIT다.** LICENSE와 exe 파일 속성에 같은 값이
  들어간다.
- **버전 문자열의 원본은 `claude_usage_overlay/version.py`의 `__version__` 하나다.**
  어디에도 버전을 두 번 적지 않는다.

---

## 파일 구조

**새로 만드는 것**

| 경로 | 책임 |
|---|---|
| `claude_usage_overlay/version.py` | 판 번호 하나. 다른 것을 담지 않는다 |
| `tests/test_version.py` | 버전이 한 군데에만 있는지 지킨다 |
| `requirements-build.txt` | CI가 설치할 판을 고정한다 |
| `.github/workflows/ci.yml` | push·PR에서 pytest |
| `.github/workflows/release.yml` | 태그 → 테스트 → 빌드 → 초안 릴리스 |
| `LICENSE` | MIT 전문 |

**고치는 것**

| 경로 | 무엇을 |
|---|---|
| `pyproject.toml` | `version` 리터럴을 빼고 `version.py`에서 끌어온다 |
| `claude_usage_overlay/tray.py` | 메뉴 맨 위에 비활성 버전 항목 |
| `tests/test_tray.py` | 그 항목을 지키는 테스트 추가 |
| `build.py` | `--noupx`, exe 파일 속성 |
| `tests/test_build.py` (신규) | 버전 튜플 변환 |
| `README.md` | "받기" 절 신설, 기존 절 재배치 |

---

## Task 1: 버전의 단일 출처

**파일:**
- 생성: `claude_usage_overlay/version.py`
- 생성: `tests/test_version.py`
- 수정: `pyproject.toml` (전체 교체)
- 수정: `claude_usage_overlay/tray.py` (import 블록, `_build_menu`)
- 수정: `tests/test_tray.py` (맨 끝에 테스트 추가)

**인터페이스:**
- 소비: 없음 (첫 작업)
- 생산:
  - `claude_usage_overlay.version.__version__: str` — `"0.1.0"`
  - `claude_usage_overlay.tray.VERSION_LABEL: str` — `f"버전 {__version__}"`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_version.py`를 만든다.

```python
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
```

- [ ] **Step 2: 테스트 실행하여 실패 확인**

실행: `python -m pytest tests/test_version.py -v`

기대 결과: `ModuleNotFoundError: No module named 'claude_usage_overlay.version'`로
세 개 모두 collection 단계에서 FAIL.

- [ ] **Step 3: `version.py` 작성**

`claude_usage_overlay/version.py`를 만든다.

```python
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
```

- [ ] **Step 4: `pyproject.toml` 교체**

전체를 아래로 바꾼다. `[build-system]`이 없으면 `[tool.setuptools.dynamic]`을
아무도 읽지 않는다 (스펙 3.6절에서 실제로 돌려 확인했다).

```toml
[project]
name = "claude-usage-overlay"
dynamic = ["version"]
requires-python = ">=3.12"
dependencies = ["pystray>=0.19", "pillow>=10.0"]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[build-system]
requires = ["setuptools>=64"]
build-backend = "setuptools.build_meta"

[tool.setuptools.dynamic]
version = { attr = "claude_usage_overlay.version.__version__" }

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 5: 테스트 실행하여 통과 확인**

실행: `python -m pytest tests/test_version.py -v`

기대 결과: 3 passed.

- [ ] **Step 6: 트레이 메뉴 테스트 작성 (실패해야 한다)**

`tests/test_tray.py` **맨 끝에** 붙인다.

```python
def test_the_menu_starts_with_a_disabled_version_item():
    """버그 제보를 받을 때 판 번호를 물어볼 유일한 수단이다.

    누를 수 있으면 안 된다 — 눌러도 아무 일이 없는 항목은 고장으로 읽힌다.
    """
    import types

    import claude_usage_overlay.tray as tray_mod
    from claude_usage_overlay.version import __version__

    stub = types.SimpleNamespace(
        _overlay=types.SimpleNamespace(is_visible=lambda: True),
        _toggle_overlay=lambda *a: None,
        _refresh_now=lambda *a: None,
        _open_settings=lambda *a: None,
        _toggle_autostart=lambda *a: None,
        _quit=lambda *a: None,
    )
    first = list(tray_mod.Tray._build_menu(stub))[0]

    assert __version__ in first.text
    assert not first.enabled
```

`Tray._build_menu(stub)`가 실제로 도는 것은 확인했다 — 이 메서드는 `self`에서
콜백 여섯과 `_overlay`만 꺼내 쓰고, 만드는 시점에 그것들을 호출하지는 않는다.

- [ ] **Step 7: 테스트 실행하여 실패 확인**

실행: `python -m pytest tests/test_tray.py::test_the_menu_starts_with_a_disabled_version_item -v`

기대 결과: 첫 항목이 `"오버레이 숨기기"`이므로
`assert '0.1.0' in '오버레이 숨기기'`에서 FAIL.

- [ ] **Step 8: `tray.py` 수정**

import 블록에 한 줄을 더한다 (`from .models import ...` 아래, 알파벳 순서에 맞게
`.winmetrics` 앞).

```python
from .version import __version__
```

`TOOLTIP_LIMIT = 128` 아래에 상수를 둔다.

```python
# 트레이 메뉴 맨 위에 그리는 판 번호. 누를 수 없는 항목이다.
VERSION_LABEL = f"버전 {__version__}"
```

`_build_menu`의 `return pystray.Menu(` 바로 다음 줄에 두 항목을 끼운다.

```python
        return pystray.Menu(
            pystray.MenuItem(VERSION_LABEL, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda _: "오버레이 숨기기" if self._overlay.is_visible() else "오버레이 보이기",
                self._toggle_overlay,
            ),
```

나머지 항목은 건드리지 않는다.

- [ ] **Step 9: 전체 테스트 실행**

실행: `python -m pytest -v`

기대 결과: 366 passed (기존 362 + 새로 넣은 4).

`test_the_menu_has_no_config_file_item`이 `tray.py` 본문을 문자열로 훑는다는 것에
주의한다. 우리가 넣은 문구에는 그 테스트가 금지하는 단어
(`설정 파일 열기`·`notepad`·`Pretendard 글꼴 설치`)가 없으므로 통과한다.

- [ ] **Step 10: 커밋**

```bash
git add claude_usage_overlay/version.py claude_usage_overlay/tray.py pyproject.toml tests/test_version.py tests/test_tray.py
git commit -m "feat: 버전을 version.py 한 곳에 두고 트레이 메뉴에 보인다"
```

---

## Task 2: `build.py` — UPX 고정과 exe 파일 속성

**파일:**
- 수정: `build.py` (상수, 새 함수 둘, `build()` 안의 명령줄)
- 생성: `tests/test_build.py`

**인터페이스:**
- 소비: `claude_usage_overlay.version.__version__` (Task 1)
- 생산:
  - `build.version_tuple(text: str) -> tuple[int, int, int, int]`
  - `build.make_version_file() -> pathlib.Path` — `build/version_info.txt`를 쓰고 그 경로를 돌려준다

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_build.py`를 만든다.

```python
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
```

- [ ] **Step 2: 테스트 실행하여 실패 확인**

실행: `python -m pytest tests/test_build.py -v`

기대 결과: `AttributeError: module 'build' has no attribute 'version_tuple'`로 2 FAIL.

- [ ] **Step 3: `build.py`에 상수와 함수를 더한다**

`ICON_SIZES = (...)` 아래에 붙인다.

```python
VERSION_FILE = ROOT / "build" / "version_info.txt"

# exe 파일 속성에 박히는 값들. LICENSE의 저작권자와 같은 이름이어야 한다.
COMPANY = "권승현"
COPYRIGHT = f"Copyright (c) 2026 {COMPANY}. MIT License."


def version_tuple(text: str) -> tuple[int, int, int, int]:
    """"0.1.0" → (0, 1, 0, 0). VS_VERSION_INFO는 네 칸을 요구한다."""
    parts = tuple(int(p) for p in text.split("."))
    return parts + (0,) * (4 - len(parts))


def make_version_file() -> Path:
    """탐색기 → 속성 → 자세히에 보일 값을 만든다.

    서명이 없는 exe는 메타데이터까지 비어 있으면 백신 오탐을 더 받는다. 그리고
    사용자가 프로그램을 띄우지 않고도 판 번호를 확인할 경로가 하나 생긴다.

    한글이 들어가도 된다 — PyInstaller가 이 파일을 UTF-8로 읽고 다시 파싱해
    같은 문자열을 돌려주는 것을 확인했다(스펙 9장 2번).
    """
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )

    from claude_usage_overlay.version import __version__

    parts = version_tuple(__version__)
    info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=parts, prodvers=parts),
        kids=[
            StringFileInfo(
                [
                    # 040904B0 = 미국 영어 + UTF-16. 문구가 한국어라도 이 코드페이지를
                    # 쓴다 — 값 자체는 UTF-16으로 들어가므로 한글이 그대로 실린다.
                    StringTable(
                        "040904B0",
                        [
                            StringStruct("CompanyName", COMPANY),
                            StringStruct("FileDescription", "Claude 사용량 오버레이"),
                            StringStruct("FileVersion", __version__),
                            StringStruct("InternalName", NAME),
                            StringStruct("LegalCopyright", COPYRIGHT),
                            StringStruct("OriginalFilename", f"{NAME}.exe"),
                            StringStruct("ProductName", "Claude Usage Overlay"),
                            StringStruct("ProductVersion", __version__),
                        ],
                    )
                ]
            ),
            VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
        ],
    )

    VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    VERSION_FILE.write_text(str(info), encoding="utf-8")
    return VERSION_FILE
```

- [ ] **Step 4: 테스트 실행하여 통과 확인**

실행: `python -m pytest tests/test_build.py -v`

기대 결과: 2 passed.

- [ ] **Step 5: `build()`의 명령줄을 고친다**

`build()` 첫 줄 아래에 버전 파일 생성을 넣는다.

```python
def build() -> int:
    icon = make_icon()
    print(f"아이콘: {icon}")

    version_file = make_version_file()
    print(f"버전 파일: {version_file}")
```

명령줄에서 `--icon` 다음에 두 줄을 끼운다.

```python
        "--icon", str(icon),
        # 빌드하는 기계에 UPX가 깔려 있으면 PyInstaller가 묻지 않고 쓴다. 그러면
        # 개발 PC와 CI가 서로 다른 exe를 낸다. 게다가 UPX로 압축된 바이너리는
        # 서명 없는 exe에 특히 나쁜 백신 오탐을 더 받는다. 축을 없앤다.
        "--noupx",
        # 탐색기 속성 창에 제품 이름·버전·저작권을 보인다.
        "--version-file", str(version_file),
```

- [ ] **Step 6: 실제로 빌드해서 확인**

실행:

```bash
python build.py
```

기대 결과: `dist\ClaudeUsageOverlay.exe`가 나고 크기가 찍힌다. 그다음 파일 속성을
확인한다.

```bash
python -c "from PyInstaller.utils.win32.versioninfo import read_version_info_from_executable as r; print(r('dist/ClaudeUsageOverlay.exe'))"
```

기대 결과: 출력에 `권승현`·`Claude 사용량 오버레이`·`0.1.0`이 보인다. **한글이
깨져 나오면** `COMPANY`와 `FileDescription`을 로마자
(`Kwon Seunghyun`, `Claude Usage Overlay`)로 바꾸고 이 단계를 다시 돈다.

- [ ] **Step 7: 난 exe를 실제로 띄워 본다**

실행: `dist\ClaudeUsageOverlay.exe`를 더블클릭한다.

기대 결과: 화면 오른쪽 아래에 오버레이가 뜨고, 트레이 아이콘 우클릭 메뉴 맨 위에
**흐린 `버전 0.1.0`**이 보이며 눌리지 않는다. 확인했으면 트레이 메뉴 → 종료.

**빌드가 exit 0인 것과 exe가 뜨는 것은 다르다.** 이 단계를 건너뛰지 않는다.

- [ ] **Step 8: 전체 테스트 실행**

실행: `python -m pytest -v`

기대 결과: 368 passed.

- [ ] **Step 9: 커밋**

```bash
git add build.py tests/test_build.py
git commit -m "build: UPX를 끄고 exe에 파일 속성을 넣는다"
```

---

## Task 3: LICENSE와 README

**파일:**
- 생성: `LICENSE`
- 수정: `README.md`

**인터페이스:**
- 소비: 없음
- 생산: 없음 (문서)

- [ ] **Step 1: `LICENSE` 작성**

파일 이름은 확장자 없이 정확히 `LICENSE`여야 GitHub이 배지를 붙인다.

```
MIT License

Copyright (c) 2026 권승현

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 2: README의 앞부분을 교체**

첫 줄 `# Claude Usage Overlay`와 그 아래 설명 한 줄은 **그대로 두고**, 그다음
`## 필요 조건` · `## 설치` · `## 실행` 세 절을 **통째로 아래 내용으로 바꾼다.**
(`## 실행 파일 만들기` 절부터는 Step 3에서 다룬다.)

바꾸는 이유는 방문자가 바뀌었기 때문이다 — 지금까지는 소스를 볼 사람만 왔지만
이제 대부분은 exe를 받으러 온다.

````markdown
## 받기

[Releases](https://github.com/Winstring08/CLAUDE_HUD/releases)에서
`ClaudeUsageOverlay.exe` 하나만 내려받으면 된다. 파이썬도 의존성도 설치 과정도
없다 — 아무 폴더에 두고 실행한다.

필요한 것은 둘이다.

- **Windows.** 트레이 아이콘 고정은 Windows 11에서만 동작하고, 나머지는 10에서도 된다
- **터미널에서 `claude auth login`이 끝나 있을 것.** 안 돼 있으면 프로그램이 떠도
  숫자를 하나도 못 보여준다

### "Windows가 PC를 보호했습니다"가 뜨면

**추가 정보 → 실행**을 누른다.

이 프로그램에는 코드 서명 인증서가 없어서 SmartScreen이 처음 보는 파일로
취급한다. 인증서는 해마다 돈이 나가는 물건이라 개인이 만든 도구에는 붙이지 않는
것이 보통이다. 경고가 뜨는 것 자체는 파일에 문제가 있다는 뜻이 아니다.

받은 파일이 릴리스에 올라온 그 파일이 맞는지는 해시로 대조한다.

```
certutil -hashfile ClaudeUsageOverlay.exe SHA256
```

나온 값이 그 릴리스의 `SHA256SUMS.txt`에 적힌 값과 같아야 한다.

## 소스로 돌리기

```bash
pip install pystray pillow
python -m claude_usage_overlay
```

트레이 메뉴의 "시작할 때 자동 실행"을 켜면 로그인 시 자동으로 뜬다. exe로 돌릴
때도 그대로 동작한다 — 레지스트리에는 파이썬 명령 대신 exe 경로가 들어간다.
````

- [ ] **Step 3: "실행 파일 만들기" 절의 성격을 바꾼다**

기존 `## 실행 파일 만들기` 절의 **제목과 첫 문단만** 아래로 바꾼다. 그 아래
문단들(exe 크기·자동 실행·프로세스 둘 이야기)은 그대로 둔다.

바꾸기 전:

```markdown
## 실행 파일 만들기

파이썬이 깔려 있지 않은 PC에서도 쓰려면 exe 하나로 묶는다.
```

바꾼 뒤:

```markdown
## 직접 빌드하기

릴리스의 exe를 그냥 쓰면 되므로 대부분은 이 절이 필요 없다. 소스를 고쳐서 자기
exe를 내려는 경우다.
```

- [ ] **Step 4: 라이선스 절을 맨 끝에 더한다**

`## 테스트` 절 아래에 붙인다.

```markdown
## 라이선스

MIT. [`LICENSE`](LICENSE)에 전문이 있다.

화면 문구에 쓰는 **Pretendard**는 SIL OFL 1.1이고 별개다. 글꼴 파일과 함께
`claude_usage_overlay/fonts/OFL.txt`가 exe 안에 들어간다.
```

- [ ] **Step 5: 링크가 실재하는지 확인**

실행:

```bash
grep -n "](" README.md
```

기대 결과: `LICENSE`와 Releases URL 둘. 로컬 파일 링크(`LICENSE`,
`claude_usage_overlay/fonts/OFL.txt`)가 실제로 있는지 `ls`로 확인한다.

- [ ] **Step 6: 커밋**

```bash
git add LICENSE README.md
git commit -m "docs: MIT 라이선스와 README 받기 절"
```

---

## Task 4: 의존성 고정과 테스트 워크플로

이 작업이 **스펙 9장 1번(CI에서 Tk 루트가 만들어지는가)을 태그 없이 확인하는
수단**이다. 릴리스 워크플로보다 먼저 한다.

**파일:**
- 생성: `requirements-build.txt`
- 생성: `.github/workflows/ci.yml`

**인터페이스:**
- 소비: 없음
- 생산: `requirements-build.txt` — `release.yml`이 같은 파일을 쓴다

- [ ] **Step 1: `requirements-build.txt` 작성**

이 판 조합에서 362개가 통과했다(스펙 3.1·3.2절). 범위가 아니라 정확한 판을 박는다
— 고정하지 않으면 어제 성공한 빌드가 오늘 깨지고, 그 사실이 태그를 민 다음에
드러난다.

```
# CI가 설치하는 판. 손으로 올리고 커밋에 남긴다.
pystray==0.19.5
pillow==12.3.0
pyinstaller==6.22.0
pytest==9.1.1
```

- [ ] **Step 2: `.github/workflows/ci.yml` 작성**

```yaml
name: 테스트

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: 의존성 설치
        run: pip install -r requirements-build.txt

      - name: pytest
        run: python -m pytest -v
```

작업 중인 모든 브랜치에 걸지 않는다. `main`으로 향하는 것만 본다.

- [ ] **Step 3: 로컬에서 같은 명령이 도는지 확인**

실행:

```bash
pip install -r requirements-build.txt
python -m pytest -v
```

기대 결과: 368 passed. 워크플로가 도는 것과 같은 명령이다.

- [ ] **Step 4: 커밋하고 PR을 올려 CI를 돌린다**

```bash
git add requirements-build.txt .github/workflows/ci.yml
git commit -m "ci: 의존성 고정과 테스트 워크플로"
git push -u origin HEAD
```

그다음 PR을 연다.

```bash
gh pr create --fill
```

- [ ] **Step 5: CI 결과를 본다 — 여기가 이 작업의 관문이다**

실행:

```bash
gh pr checks --watch
```

**기대 결과: 통과.** 통과하면 `tests/conftest.py`의 `tk.Tk()`가 `windows-latest`에서
만들어진다는 뜻이고, 스펙 9장 1번이 해소된다.

**실패하면** 로그를 본다.

```bash
gh run view --log-failed
```

Tk 관련 실패(`no display name`·`couldn't connect to display`·`TclError`)라면 그때
정한다 — 이 플랜은 대안을 미리 고르지 않는다. **정하기 전에 사람에게 알린다.**
Tk와 무관한 실패라면 원인을 고치고 다시 민다.

**여기서 CI가 통과할 때까지 Task 5로 넘어가지 않는다.**

---

## Task 5: 릴리스 워크플로

**파일:**
- 생성: `.github/workflows/release.yml`

**인터페이스:**
- 소비: `requirements-build.txt` (Task 4), `claude_usage_overlay.version.__version__` (Task 1), `build.py`의 산출물 `dist/ClaudeUsageOverlay.exe` (Task 2)
- 생산: 없음

- [ ] **Step 1: `.github/workflows/release.yml` 작성**

```yaml
name: 릴리스

on:
  push:
    tags: ['v*']

# gh release create가 릴리스를 만들려면 쓰기 권한이 필요하다.
permissions:
  contents: write

jobs:
  release:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: 의존성 설치
        run: pip install -r requirements-build.txt

      # 여기서 멈추면 릴리스는 만들어지지 않는다. 순서가 곧 안전장치다.
      - name: 태그와 version.py 대조
        shell: bash
        run: |
          TAG="${GITHUB_REF_NAME#v}"
          SRC=$(python -c "from claude_usage_overlay.version import __version__; print(__version__)")
          echo "태그 $TAG / 소스 $SRC"
          if [ "$TAG" != "$SRC" ]; then
            echo "::error::태그($TAG)와 version.py($SRC)가 다르다"
            exit 1
          fi

      - name: pytest
        run: python -m pytest -v

      - name: 빌드
        run: python build.py

      # sha256sum 대신 PowerShell을 쓴다 — 러너에 coreutils가 있는지에 기대지
      # 않는다. 출력 형식은 sha256sum과 같게 맞춰, 받는 쪽이 흔한 도구로 대조할
      # 수 있게 한다.
      - name: SHA-256
        shell: pwsh
        run: |
          $h = (Get-FileHash dist\ClaudeUsageOverlay.exe -Algorithm SHA256).Hash.ToLower()
          "$h  ClaudeUsageOverlay.exe" | Out-File -Encoding ascii dist\SHA256SUMS.txt
          Get-Content dist\SHA256SUMS.txt

      # 초안으로 만든다. 사람이 노트를 다듬고 게시할 때까지 아무에게도 알림이
      # 가지 않는다. 서드파티 액션을 쓰지 않는 이유는 그것이 태그가 조용히
      # 옮겨질 수 있는 공급망 표면이기 때문이다 — gh는 러너에 이미 있다.
      - name: 초안 릴리스 생성
        shell: bash
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          gh release create "$GITHUB_REF_NAME" \
            --draft \
            --title "$GITHUB_REF_NAME" \
            --notes "노트를 채우고 게시한다." \
            dist/ClaudeUsageOverlay.exe \
            dist/SHA256SUMS.txt
```

- [ ] **Step 2: 커밋하고 민다**

```bash
git add .github/workflows/release.yml
git commit -m "ci: 태그를 밀면 초안 릴리스를 만드는 워크플로"
git push
```

- [ ] **Step 3: PR의 CI가 여전히 통과하는지 확인**

실행: `gh pr checks --watch`

기대 결과: 통과. `release.yml`은 태그에만 걸리므로 이 PR에서는 돌지 않는다 —
문법 오류가 있어도 여기서는 안 잡힌다는 뜻이다. 실제 검증은 Task 6이다.

---

## Task 6: 첫 릴리스 `v0.1.0`

여기서 파이프라인 전체가 처음으로 실제로 돈다.

**파일:** 없음 (실행만)

**인터페이스:**
- 소비: Task 1–5 전부
- 생산: 없음

- [ ] **Step 1: PR을 머지한다**

```bash
gh pr merge --squash
git checkout main
git pull
```

- [ ] **Step 2: main에서 CI가 통과하는지 확인**

실행:

```bash
gh run watch
```

기대 결과: `테스트` 워크플로 통과. **머지가 성공한 것과 머지된 main이 통과하는
것은 다르다.** 여기를 보고 나서 태그를 민다.

- [ ] **Step 3: 태그를 민다**

```bash
git tag -a v0.1.0 -m "v0.1.0"
git push origin v0.1.0
```

- [ ] **Step 4: 릴리스 워크플로를 지켜본다**

실행:

```bash
gh run watch
```

기대 결과: `릴리스` 워크플로의 여섯 step이 전부 통과.

실패하면 `gh run view --log-failed`로 원인을 본다. 고친 뒤에는 **태그를 지우고
같은 번호로 다시 민다** — 아직 아무도 못 봤으므로 재사용해도 된다. 게시한
다음에는 재사용하지 않는다.

```bash
git push --delete origin v0.1.0 && git tag -d v0.1.0
```

- [ ] **Step 5: 초안이 생겼는지 확인**

실행:

```bash
gh release view v0.1.0
```

기대 결과: `draft: true`, 첨부 파일 `ClaudeUsageOverlay.exe`와 `SHA256SUMS.txt` 둘.

- [ ] **Step 6: CI가 낸 exe를 내려받아 실제로 띄운다 — 이 플랜의 마지막 관문**

```bash
gh release download v0.1.0 --dir ./_check
```

그다음 확인한다.

1. 해시가 맞는지: `certutil -hashfile _check\ClaudeUsageOverlay.exe SHA256`의 값이
   `_check\SHA256SUMS.txt`와 같은가
2. `_check\ClaudeUsageOverlay.exe`를 더블클릭했을 때 오버레이가 뜨고 트레이 메뉴에
   `버전 0.1.0`이 흐리게 보이는가
3. 속성 → 자세히에 제품 이름과 저작권이 보이는가

**빌드가 통과한 것과 exe가 뜨는 것은 다르다.** 셋 다 확인한 뒤 `_check`를 지운다.

- [ ] **Step 7: 릴리스 노트를 쓰고 게시한다**

자동 생성에 맡기지 않는다 — 커밋 제목이 한국어 관용문이라 자동 목록은 읽는
사람에게 뜻이 서지 않는다. 첫 판이므로 무엇을 하는 프로그램인지부터 쓴다.

노트에 반드시 들어갈 것:

- 무엇을 하는 프로그램인가 한두 줄
- **`claude auth login`이 끝나 있어야 한다**는 전제
- SmartScreen 경고가 뜬다는 것과 넘는 법 (추가 정보 → 실행)
- SHA-256 대조법

**게시는 사람이 판단한다.** 노트를 준비한 뒤 사용자에게 확인을 받고 나서 누른다.

- [ ] **Step 8: 게시된 릴리스를 확인한다**

실행:

```bash
gh release view v0.1.0
```

기대 결과: `draft: false`. 저장소 첫 화면 오른쪽에 Releases와 MIT 배지가 보인다.

---

## 완료 기준

여섯 개가 전부 참이어야 끝난 것이다.

- [ ] `python -m pytest -v`가 368개 통과
- [ ] `main`에서 `테스트` 워크플로가 통과
- [ ] `v0.1.0` 태그가 릴리스 워크플로를 통과시켜 초안을 만들었다
- [ ] 그 초안의 exe를 내려받아 **실행해 봤고** 트레이 메뉴에 `버전 0.1.0`이 보였다
- [ ] 해시가 `SHA256SUMS.txt`와 일치했다
- [ ] 릴리스가 게시되어 있고 저장소에 MIT 배지가 붙었다
