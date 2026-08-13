# 설정창과 오버레이 개편 구현 플랜

> **구현 완료 (2026-08-13).** 이 플랜은 기록으로 남긴다. 실행할 문서가 아니다.
>
> **Task 7·14가 선 전제 하나가 틀렸다.** "트레이 아이콘 고정은 즉시 반영되지
> 않는다 · 다음 로그온부터"는 재현되지 않았다 — 그 실측이 Claude Code(MSIX 패키지
> 앱)의 셸에서 띄운 인스턴스로 이루어졌고, 패키지 컨테이너 안에서는 `HKCU`와
> `%APPDATA%` 쓰기가 패키지 전용 저장소로 재지정되어 탐색기가 그 값을 못 본다.
> 컨테이너 밖에서는 예외 없이 즉시 반영된다. 자세한 것은 설계 문서 2.2절의 정정.
>
> 그 결과 **Task 14의 첫 실행 안내창은 통째로 없앴고**(사용자가 할 일이 없으므로
> 알릴 것도 없다), 안내 문구 셋도 사라지거나 바뀌었다. 아래 본문에 남은
> "다음 로그온부터" 서술은 전부 그 정정 이전의 것이다.

> **에이전트에게:** 이 플랜이 완전한 작업 명세다. 한 번 읽고 끝까지 구현한다. 진행 표시는 체크박스(`- [ ]`)를 쓴다.

**목표:** 메모장으로 고치던 `config.json`을 GUI 설정창으로 대체하고, 오버레이를 평소 66×66 정사각형으로 줄이면서 지금 모습을 "자세히 보기"로 옮긴다. 트레이 아이콘 고정과 Pretendard 글꼴 번들을 함께 넣는다.

**아키텍처:** 판단은 순수 함수로 빼고 UI는 얇게 — 기존 `ring_render`·`icon_render`가 쓰는 방식을 따른다. 캔버스에 직접 그리는 위젯 셋(체크박스·슬라이더·드롭다운)은 각각 파일 하나이고, 값↔픽셀 환산과 클램프·스냅은 창 없이 테스트한다. 설정창은 초안(`Draft`)을 들고 있다가 닫을 때 공유 `Config` 객체에 한 번에 커밋하고, 폴러·오버레이·트레이가 매 틱 그 객체를 다시 읽으므로 재시작 안내가 필요 없다.

**기술 스택:** Python 3.12, tkinter 8.6(표준 라이브러리), pystray, pillow, winreg·ctypes(표준 라이브러리), pytest(개발 전용)

## 전역 제약

- Python 3.12 전용. `str | None` 등 3.10+ 문법을 쓴다.
- **Windows 전용.** macOS/Linux 지원은 범위 밖이다.
- **런타임 외부 의존성은 `pystray`와 `pillow` 둘뿐이다.** 새 의존성을 추가하지 않는다.
- 사용자에게 보이는 모든 문구는 한국어로 쓴다.
- **드라이브 문자를 하드코딩하지 않는다.** 윈도우 경로는 `%WINDIR%`·`%LOCALAPPDATA%`·`%APPDATA%` 환경변수로 조립한다. `winmetrics.py`가 이미 그렇게 하고 있다.
- **모든 픽셀 치수는 기준값 × `winmetrics.dpi_scale()`이다.** 글꼴 크기는 **음수 픽셀**로 준다 — 양수(포인트)로 주면 `tk scaling`이 이미 반영한 배율에 한 번 더 곱해져 150%에서 글자만 창을 넘는다. `overlay.fonts_for()`의 주석에 근거가 있다.
- **레지스트리는 HKCU만 건드린다.** 관리자 권한이 필요한 경로에 쓰지 않는다.
- **실패해도 프로그램은 뜬다.** DWM 어두운 제목 표시줄·레지스트리 아이콘 고정·글꼴 번들 로드는 전부 실패하면 조용히 넘어간다. 예외를 밖으로 던지지 않는다 — `pythonw`에는 콘솔이 없어 원인이 아무 데도 남지 않는다.
- **`Config`에 없는 값은 레지스트리가 진짜 상태다.** 자동 실행과 트레이 아이콘 고정은 `config.json`에 저장하지 않고, 화면을 그릴 때마다 레지스트리에서 읽는다.
- `.spec` 파일에 손대지 않는다. `build.py`가 PyInstaller에 인자를 직접 넘기므로 `ClaudeUsageOverlay.spec`은 아무도 읽지 않는 빌드 부산물이고 `.gitignore`가 이미 걸러낸다. 빌드 설정을 바꾸는 자리는 `build.py`의 인자 목록 한 곳뿐이다.
- 테스트는 창을 띄우지 않는다. Tk 인스턴스가 필요한 것은 `tests/test_overlay_layout.py`처럼 `root.withdraw()`한 모듈 스코프 픽스처를 쓴다.
- 명령은 저장소 루트(`C:\Users\r46t8\IdeaProjects\CLAUDE_HUD`)에서 실행한다. 테스트는 `python -m pytest`다.

---

## 파일 구조

```
claude_usage_overlay/
  fonts/                    (신규) Pretendard TTF 둘 + OFL.txt. exe에 함께 묶인다
  widget_paint.py           (신규) 위젯 셋이 공유하는 PIL 조각 — 둥근 사각형·원
  text_center.py            (신규) 잉크 상자를 재서 상자 중앙에 놓는 좌표 계산
  checkbox.py               (신규) 캔버스 체크박스
  slider.py                 (신규) 캔버스 슬라이더. 값↔픽셀·클램프·5단위 스냅은 순수 함수
  dropdown.py               (신규) 캔버스 드롭다운
  settings_window.py        (신규) 설정창 Toplevel. 초안을 들고 있다가 닫을 때 커밋
  tray_promote.py           (신규) NotifyIconSettings 항목 찾기·읽기·쓰기
  first_run.py              (신규) 첫 실행 판정과 안내창
  overlay.py                두 모드, 클릭 전환, 우클릭 메뉴, 3px 판정, 갱신 지연
  theme.py                  색 교체 (링은 밝게 · 채움은 어둡게, 같은 견본의 두 단계)
  config.py                 UI_OWNED 제거, overlay_detailed 추가, warn/danger 보정
  formatting.py             format_ring_time 추가
  font_install.py           번들 로드만 남김. 다운로드·압축 해제·레지스트리 등록 삭제
  winmetrics.py             dark_title_bar 추가
  tray.py                   메뉴 개편
  __main__.py               첫 실행 판정, 아이콘 고정 시도, 설정창 배선
  build.py                  글꼴 --add-data 추가
tests/
  test_text_center.py       (신규)
  test_widget_paint.py      (신규)
  test_checkbox.py          (신규)
  test_slider.py            (신규)
  test_dropdown.py          (신규)
  test_settings_window.py   (신규)
  test_tray_promote.py      (신규)
  test_first_run.py         (신규)
  test_overlay_modes.py     (신규) 기본 모드 · 갱신 지연 · 3px 판정 · 모드 전환 위치
  test_config.py            UI_OWNED 관련 테스트 갱신
  test_font_install.py      다운로드·압축 해제 판정 삭제, activate 몫만 남김
  test_overlay_layout.py    자세히 모드 근거로 남기고 기본 모드 몫 추가
```

**`widget_paint.py`는 스펙 10장의 모듈 표에 없는 파일이다.** 체크박스·슬라이더·
드롭다운이 같은 둥근 사각형을 그리므로 세 번 베끼는 대신 한 곳에 모았다.

### 왜 잉크 상자를 PIL로 재는가 (실측 근거)

스펙 2.6절은 "그릴 때마다 잉크 상자를 재라"고 하지만 **tkinter는 문자열의 잉크
상자를 알려주지 않는다** — `Font.metrics()`에는 ascent·descent·linespace만 있고
`Canvas.bbox()`는 잉크가 아니라 레이아웃 상자다. 그래서 잉크는 PIL로 글꼴 파일을
직접 열어 재고, Tk 좌표로는 **baseline을 경유해서** 옮긴다.

ascender선을 경유하면 안 된다. Tk와 PIL이 ascent를 다르게 센다 (실측):

| 글꼴 | px | Tk ascent | PIL ascent |
|---|---|---|---|
| Pretendard Bold | 15 | 14 | 15 |
| Pretendard Bold | 18 | 17 | 18 |
| Pretendard Bold | 22 | 21 | 21 |
| Segoe UI Bold | 15 | 16 | 17 |
| Segoe UI Bold | 18 | 20 | 20 |

baseline 기준 값은 글꼴 파일 자체의 성질이라 양쪽이 같다. 공식은 이렇다.

```
잉크높이  = ink.bottom - ink.top                     (baseline 기준, top은 음수)
잉크위치  = box_top + (box_h - 잉크높이) // 2         (floor → 남는 반 픽셀이 위로)
nw_y      = 잉크위치 - tk_ascent - ink.top
```

**이 공식이 스펙 2.6절의 실측을 정확히 재현한다.** Pretendard 18px `100`,
링 안쪽 상자 top=13 · 높이=40에서:

- PIL: ascent 18, `getbbox("100")` = (0, 5, 33, 18) → baseline 기준 top −13, bottom 0, 높이 13 (스펙의 "잉크는 13px" ✓)
- 잉크위치 = 13 + (40 − 13) // 2 = 26 → `nw_y` = 26 − 17 + 13 = **22**
- 잉크는 26~38 픽셀을 덮고 위 여백 13 · 아래 여백 14 (스펙 표의 y=32 행과 같다 ✓)
- 스펙이 쓴 `anchor="center"` y=32는 레이아웃 상자 높이 21에서 상자 top이 32 − 21//2 = **22**다. 두 경로가 독립적으로 같은 값에 닿았다

`round()`를 쓰면 안 된다. 파이썬의 `round()`는 은행가 반올림이라
`round(1.5)=2`(아래)·`round(2.5)=2`(위)로 값의 홀짝에 따라 방향이 갈린다.
`//`(floor)로 명시해야 "남는 반 픽셀은 위로"가 지켜진다.

---

## Task 1: Pretendard 번들

exe에 글꼴을 넣어 다운로드·설치 개념을 없앤다. `font_install.py`가 하던 일 중
번들 로드만 남고, 트레이 메뉴의 "Pretendard 글꼴 설치" 항목이 사라진다.

**파일:**
- 생성: `claude_usage_overlay/fonts/Pretendard-Regular.ttf`, `claude_usage_overlay/fonts/Pretendard-Bold.ttf`, `claude_usage_overlay/fonts/OFL.txt`
- 수정: `claude_usage_overlay/font_install.py` (전면 축소), `claude_usage_overlay/tray.py:10,147-153,169-193`, `build.py:56-67`
- 테스트: `tests/test_font_install.py` (전면 교체)

**인터페이스:**
- 제공:
  - `font_install.BUNDLE_FILES: tuple[str, str]` — `("Pretendard-Regular.ttf", "Pretendard-Bold.ttf")`
  - `font_install.bundle_dir() -> Path`
  - `font_install.activate(fonts_dir: Path | None = None) -> int`
  - `font_install.font_file_for(family: str, bold: bool = True) -> Path | None`
- 사라짐: `fetch_zip` · `pick_zip_asset` · `wanted_members` · `extract_to` · `register` · `install` · `is_installed` · `registry_value_name` · `WANTED_FILES` · `RELEASE_API` · `FONTS_REG_KEY`

- [ ] **Step 1: 글꼴 파일을 저장소에 넣는다**

TTF 둘은 지금 코드의 다운로드 경로를 그대로 써서 받는다. 47MB를 받아 필요한
둘(5.4MB)만 꺼낸다.

```bash
python -c "from pathlib import Path; from claude_usage_overlay.font_install import extract_to, fetch_zip; print(extract_to(fetch_zip(), Path('claude_usage_overlay/fonts')))"
```

이미 계정 글꼴 폴더에 깔아둔 경우에는 복사가 더 빠르다 (같은 파일이다).

```bash
mkdir -p claude_usage_overlay/fonts && cp "$LOCALAPPDATA/Microsoft/Windows/Fonts/Pretendard-Regular.ttf" "$LOCALAPPDATA/Microsoft/Windows/Fonts/Pretendard-Bold.ttf" claude_usage_overlay/fonts/
```

라이선스 파일을 함께 넣는다. SIL OFL 1.1은 저작권 표시와 라이선스 파일 동봉을
조건으로 번들·재배포를 허용한다.

```bash
curl -L -o claude_usage_overlay/fonts/OFL.txt https://raw.githubusercontent.com/orioncactus/pretendard/main/LICENSE
```

- [ ] **Step 2: 받은 것을 확인한다**

```bash
ls -l claude_usage_overlay/fonts && head -3 claude_usage_overlay/fonts/OFL.txt
```

예상: TTF 둘이 각각 2.6MB·2.7MB, `OFL.txt` 첫 줄에 `SIL OPEN FONT LICENSE`.
라이선스 첫 줄이 다르면 여기서 멈추고 사람에게 알린다 — 엉뚱한 파일을 동봉하면
번들 자체가 성립하지 않는다.

- [ ] **Step 3: 실패하는 테스트 작성**

`tests/test_font_install.py`를 통째로 아래 내용으로 바꾼다. 다운로드·압축 해제
판정은 그 코드가 사라지므로 함께 사라진다.

```python
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
```

- [ ] **Step 4: 테스트를 돌려 실패 확인**

```bash
python -m pytest tests/test_font_install.py -v
```

예상: `ImportError: cannot import name 'BUNDLE_FILES'`로 수집 단계에서 FAIL.

- [ ] **Step 5: `font_install.py`를 통째로 교체**

```python
"""번들 Pretendard를 이 프로세스에 올린다.

이 프로그램의 문구는 한국어인데 Segoe UI에는 한글 글리프가 없다. 그대로 두면
숫자·영문과 한글이 서로 다른 글꼴로 그려진다. Pretendard는 둘을 한 글꼴로 덮지만
윈도우 기본 글꼴이 아니다.

**그래서 exe에 함께 묶는다.** 예전에는 트레이 메뉴로 47MB를 받아 계정 글꼴
폴더에 설치했는데, 번들이면 첫 실행부터 Pretendard다 — 기다림 0초, 네트워크 0,
실패 경로 0이다. 계정 글꼴 폴더에도 레지스트리에도 쓰지 않는다.

**GDI는 글꼴 파일을 잠그지 않는다(실측).** AddFontResourceW로 올린 채 파일을
지워도, 폴더를 통째로 지워도 성공한다. 그래서 단일 파일 exe가 종료할 때 임시
폴더를 지우는 동작이 그대로 성공하고, 종료 시 RemoveFontResourceW를 부를 필요도
찌꺼기 걱정도 없다.
"""

import ctypes
import sys
from pathlib import Path

from .winmetrics import fonts_dir

# static TTF 둘만 넣는다.
#
# variable(PretendardVariable.ttf)은 쓰지 않는다. 패밀리 이름이 "Pretendard
# Variable"로 따로 잡히는 데다 GDI가 굵기 축을 다루지 못해, bold를 요청하면
# 진짜 Bold 대신 합성된 가짜 굵기가 나온다. static Bold를 같이 올리면 그럴 일이 없다.
BUNDLE_FILES = ("Pretendard-Regular.ttf", "Pretendard-Bold.ttf")

# Tk 패밀리 이름 → TTF 파일. 잉크 상자를 재려면 파일이 필요하다 (text_center 머리말).
#
# 표로 두는 이유는 우리가 화면에 쓰는 글꼴이 둘뿐이기 때문이다 — 번들 Pretendard와,
# 번들 로드가 실패했을 때의 폴백 Segoe UI. 일반적인 패밀리→파일 해석은 레지스트리를
# 훑어야 하고 이름이 로케일에 따라 달라져 깨지기 쉽다. 표에 없는 이름이 오면
# None이고, 그때는 부르는 쪽이 잉크 정렬을 포기한다.
SEGOE_FILES = {True: "segoeuib.ttf", False: "segoeui.ttf"}


def bundle_dir() -> Path:
    """번들 글꼴이 있는 폴더.

    소스로 돌릴 때는 패키지 안의 fonts/, 단일 파일 exe로 돌릴 때는 부트로더가
    자기 자신을 풀어놓은 sys._MEIPASS 아래다. 후자를 안 보면 exe에서 글꼴을
    못 찾아 화면이 조용히 Segoe UI로 떨어진다.
    """
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "claude_usage_overlay" / "fonts"
    return Path(__file__).resolve().parent / "fonts"


def font_file_for(family: str, bold: bool = True) -> Path | None:
    """Tk 패밀리 이름 → TTF 파일 경로. 모르는 이름이면 None."""
    name = family.lower()
    if name.startswith("pretendard"):
        path = bundle_dir() / ("Pretendard-Bold.ttf" if bold else "Pretendard-Regular.ttf")
        return path if path.exists() else None
    if name == "segoe ui":
        path = fonts_dir() / SEGOE_FILES[bold]
        return path if path.exists() else None
    return None


def activate(fonts_dir: Path | None = None) -> int:
    """번들 글꼴을 **이 프로세스에서 쓸 수 있게** 올린다. 올린 개수 반환.

    AddFontResourceW로 올린 글꼴은 올린 프로세스가 살아 있는 동안만 시스템 글꼴
    목록에 남는다. 계정에 설치하는 것이 아니므로 매 기동마다 불러야 한다.

    **Tk()를 만들기 전에 불러야 한다.** Tk는 시작할 때 글꼴 목록을 읽는다.

    실패해도 조용히 넘어간다. 그때는 pick_font_family가 Segoe UI로 떨어뜨린다.
    """
    directory = fonts_dir or bundle_dir()
    loaded = 0
    for name in BUNDLE_FILES:
        path = directory / name
        if not path.exists():
            continue
        try:
            if ctypes.windll.gdi32.AddFontResourceW(ctypes.c_wchar_p(str(path))):
                loaded += 1
        except (AttributeError, OSError):
            pass
    return loaded
```

- [ ] **Step 6: 트레이 메뉴에서 글꼴 항목을 뺀다**

`claude_usage_overlay/tray.py`에서 세 곳을 고친다.

1. 행 10: `from . import autostart, font_install` → `from . import autostart`
2. 행 148-153: 주석 `# 이미 깔려 있는 사람에게는...`과 그 아래
   `pystray.MenuItem("Pretendard 글꼴 설치", ...)` 항목 전체 삭제.
   **행 147의 `"설정 파일 열기"` 항목은 그대로 둔다** — 그것은 Task 15에서 없어진다
3. 행 169-193의 `_install_font` · `_install_font_now` · `_notify` 메서드 삭제

`_notify`도 함께 지운다 — 부르는 곳이 글꼴 설치뿐이었고, 스펙 3.3절이 오버레이
숨기기에도 풍선 알림을 띄우지 않기로 정했다. 쓰이지 않는 `import threading`도
지운다 (다른 곳에서 안 쓴다).

- [ ] **Step 7: `build.py`에 글꼴을 넣는다**

`build.py` 상단 import에 `import os`를 추가하고, `cmd` 목록의
`"--hidden-import", "PIL._tkinter_finder",` 다음 줄에 넣는다.

```python
        # 글꼴은 정적 분석에 안 잡힌다. 우리가 경로로 여는 데이터 파일이다.
        # 구분자는 os.pathsep — 윈도우에서는 ';'다.
        "--add-data",
        f"{ROOT / 'claude_usage_overlay' / 'fonts'}{os.pathsep}claude_usage_overlay/fonts",
```

- [ ] **Step 8: 테스트를 돌려 통과 확인**

```bash
python -m pytest tests/test_font_install.py tests/test_tray.py -v
```

예상: 전부 PASS.

- [ ] **Step 9: 전체 테스트로 회귀 확인**

```bash
python -m pytest -q
```

예상: 실패 0. `tray.py`에서 지운 것을 다른 곳이 참조하고 있으면 여기서 잡힌다.

- [ ] **Step 10: 커밋**

```bash
git add claude_usage_overlay/fonts claude_usage_overlay/font_install.py claude_usage_overlay/tray.py build.py tests/test_font_install.py
git commit -m "feat: Pretendard를 exe에 번들해 다운로드·설치 경로를 없앰"
```

---

## Task 2: 색 교체

링과 채움을 **같은 견본의 밝기 두 단계**로 만든다. 지금은 두 색표가 서로 무관한
색인데, 링은 어두운 창 위의 5px 선이라 밝아야 하고 채움은 흰 숫자를 얹는 바탕이라
어두워야 한다는 관계 자체는 그대로다.

**파일:**
- 수정: `claude_usage_overlay/theme.py:3-5,26-28`
- 테스트: `tests/test_theme.py` (추가), `tests/test_icon_render.py` (건드리지 않는다 — 상수를 참조하므로 자동으로 새 값을 잰다)

**인터페이스:**
- 제공: `theme.GREEN` · `YELLOW` · `RED` · `FILL_GREEN` · `FILL_YELLOW` · `FILL_RED` (이름 그대로, 값만 바뀐다)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_theme.py` 끝에 붙인다.

```python
def _rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def _luminance(hex_color):
    def channel(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in _rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b):
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# 스펙 7장의 표. **눈으로 고른 값이라 재현 규칙이 없다** — 명도를 몇 % 옮겼다는
# 서술은 근사일 뿐이고 정본은 이 hex다.
CHOSEN = {
    "GREEN": "#69ba7a",
    "YELLOW": "#f4b044",
    "RED": "#e8696b",
    "FILL_GREEN": "#449354",
    "FILL_YELLOW": "#c9800c",
    "FILL_RED": "#dc2224",
}

# 견본 그대로 쓰면 노란 구간이 여기까지 떨어진다 (스펙 2.7절 실측).
RAW_SAMPLE_YELLOW_CONTRAST = 1.71


def test_the_colors_are_the_ones_that_were_chosen_by_eye():
    """트레이에 세 팔레트를 동시에 띄워 비교한 뒤 정한 값이다. 계산으로 다시
    만들어낼 수 없으므로 여기 적어 묶어둔다."""
    for name, value in CHOSEN.items():
        assert getattr(theme, name) == value, name


def test_white_numbers_stay_readable_on_every_fill():
    """트레이 아이콘은 채움 위에 흰 숫자를 얹는다. 견본(#f3a72e)을 그대로 쓰면
    1.71:1까지 떨어져 기존 theme.py 주석이 "사실상 읽히지 않는다"고 적어둔
    구간에 들어간다. 어둡게 한 뒤에는 2.69:1이다 (스펙 2.7절)."""
    for name in ("FILL_GREEN", "FILL_YELLOW", "FILL_RED"):
        got = _contrast(getattr(theme, name), theme.TEXT_LIGHT)
        assert got > RAW_SAMPLE_YELLOW_CONTRAST + 0.9, f"{name}: {got:.2f}"


def test_ring_is_brighter_than_the_matching_fill():
    """한 색의 밝기 두 단계다. 링은 어두운 창 위의 5px 선이라 밝아야 하고,
    채움은 흰 숫자를 얹는 바탕이라 어두워야 한다."""
    for ring, fill in (
        (theme.GREEN, theme.FILL_GREEN),
        (theme.YELLOW, theme.FILL_YELLOW),
        (theme.RED, theme.FILL_RED),
    ):
        assert _luminance(ring) > _luminance(fill), f"{ring} vs {fill}"


def test_ring_stays_visible_on_the_window_background():
    """5px 선이라 4.0:1이면 충분하다. 이 아래로 내려가면 노란 링이 배경에 묻힌다."""
    for ring in (theme.GREEN, theme.YELLOW, theme.RED):
        assert _contrast(ring, theme.BG) >= 4.0, ring
```

- [ ] **Step 2: 테스트를 돌려 실패 확인**

```bash
python -m pytest tests/test_theme.py -v
```

예상: `test_the_colors_are_the_ones_that_were_chosen_by_eye`가 FAIL —
지금 값이 `#63e6be`·`#f6c177`·`#ff8f8f`·`#059669`·`#d97706`·`#dc2626`이다.
나머지 셋은 지금도 통과한다. **그게 맞다** — 그 셋은 교체를 감지하는 관문이
아니라 앞으로 색을 만질 때 넘지 말아야 할 바닥을 지키는 관문이다.
지금 값도 그 바닥 위에 있으므로 통과하는 것이 정상이다.

- [ ] **Step 3: `theme.py`의 색을 바꾼다**

3~5행:

```python
# 링 색과 채움 색은 **같은 견본의 밝기 두 단계**다. 견본은 #4ca45e · #f3a72e ·
# #e3484a 셋이고, 색상과 채도는 건드리지 않고 명도만 옮겼다 (HSL 채도 실측:
# 초록 36.7 → 37.0 → 36.7, 노랑 89.1 → 88.9 → 88.7, 빨강 73.5 → 73.4 → 73.2).
#
# 여기(링)는 견본에서 **밝힌** 쪽이다. 어두운 창 위에 그리는 5px 선이라
# 밝아야 보인다. 눈으로 고른 값이라 "명도 +30%" 같은 재현 규칙은 없다 —
# 정본은 이 hex다.
GREEN = "#69ba7a"
YELLOW = "#f4b044"
RED = "#e8696b"
```

26~28행:

```python
# 여기(채움)는 견본에서 **어둡게 한** 쪽이다. 흰 숫자를 얹는 바탕이라 어두워야
# 읽힌다 — 밝은 채움 위의 흰 글자는 대비가 1.7까지 떨어져 사실상 안 읽힌다.
# 트레이에 세 팔레트를 동시에 띄워 비교한 뒤 정했다 (스펙 2.7절).
FILL_GREEN = "#449354"
FILL_YELLOW = "#c9800c"
FILL_RED = "#dc2224"
```

- [ ] **Step 4: 테스트를 돌려 통과 확인**

```bash
python -m pytest tests/test_theme.py tests/test_icon_render.py -v
```

예상: 전부 PASS. `test_icon_render.py`의 `MIN_FILL_CONTRAST = 2.5` 관문도
새 값(최저 2.69)이 통과한다.

- [ ] **Step 5: 커밋**

```bash
git add claude_usage_overlay/theme.py tests/test_theme.py
git commit -m "feat: 링·채움 색을 같은 견본의 밝기 두 단계로 교체"
```

---

## Task 3: config 개편

`UI_OWNED`가 사라지고 저장이 전체 쓰기로 단순해진다. 새 필드
`overlay_detailed`가 붙고, `warn ≥ danger`를 불러올 때 바로잡는다.

**파일:**
- 수정: `claude_usage_overlay/config.py` (전면)
- 테스트: `tests/test_config.py` (일부 교체)

**인터페이스:**
- 제공:
  - `config.Config` — 필드 `poll_seconds: int = 300` · `warn_pct: int = 70` · `danger_pct: int = 90` · `overlay_visible: bool = True` · `overlay_detailed: bool = False`
  - `config.MIN_POLL_SECONDS: int = 120`
  - `config.PCT_STEP: int = 5` — 사용률 슬라이더 단위이자 노란·빨간 사이 최소 간격
  - `config.PCT_MIN: int = 50` · `config.PCT_MAX: int = 100`
  - `config.load_config(path=None) -> Config` · `config.save_config(cfg, path=None) -> None` · `config.config_path() -> Path`
- 사라짐: `config.UI_OWNED`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_config.py`에서 `test_manual_edits_survive_a_position_save`(80-96행)를
지우고 아래를 붙인다. 그 테스트의 근거였던 "사용자가 메모장으로 고친다"가
사라졌으므로 함께 사라진다.

```python
def test_overlay_detailed_defaults_to_the_basic_mode(tmp_path):
    """기본값이 false인 쪽이 기본 모드와 일치해서 파일을 열어본 사람이
    헷갈리지 않는다 (스펙 9장)."""
    assert load_config(tmp_path / "none.json").overlay_detailed is False


def test_overlay_detailed_only_accepts_a_real_bool(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"overlay_detailed": "true"}), encoding="utf-8")
    assert load_config(p).overlay_detailed is False   # 버리고 기본값

    p.write_text(json.dumps({"overlay_detailed": True}), encoding="utf-8")
    assert load_config(p).overlay_detailed is True


def test_save_writes_the_whole_file(tmp_path):
    """이제 전부 GUI가 소유한다. 부분 병합이 없어졌으므로 디스크의 옛 키가
    남아 있으면 안 된다 — 남으면 다음 판올림에서 사라진 필드가 되살아난다."""
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"poll_seconds": 900, "옛날키": 1}), encoding="utf-8")
    save_config(Config(poll_seconds=600), p)
    written = json.loads(p.read_text(encoding="utf-8"))
    assert set(written) == set(Config.__dataclass_fields__)
    assert written["poll_seconds"] == 600


def test_ui_owned_is_gone():
    """부분 병합의 근거였던 '나머지는 메모장으로 고치는 값'이 사라졌다.
    상수가 남아 있으면 다음 사람이 그 규칙이 아직 산다고 읽는다."""
    assert not hasattr(config, "UI_OWNED")


def test_warn_above_danger_is_corrected_on_load(tmp_path):
    """warn ≥ danger면 노란색이 영영 안 나온다. 설정창에서만 고치면 창을 한 번도
    안 연 사람은 그대로 남으므로 불러올 때 바로잡는다 (스펙 4.1절)."""
    p = tmp_path / "config.json"
    for warn, danger in ((95, 90), (90, 90), (100, 60)):
        p.write_text(json.dumps({"warn_pct": warn, "danger_pct": danger}), encoding="utf-8")
        cfg = load_config(p)
        assert cfg.danger_pct == danger, "danger를 기준으로 두고 warn을 내린다"
        assert cfg.warn_pct == danger - config.PCT_STEP


def test_the_correction_never_pushes_warn_below_zero(tmp_path):
    """손으로 danger=2를 적어둔 경우다. 음수 임계값을 만들면 안 된다."""
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"warn_pct": 50, "danger_pct": 2}), encoding="utf-8")
    assert load_config(p).warn_pct == 0


def test_a_sane_pair_is_left_alone(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"warn_pct": 60, "danger_pct": 80}), encoding="utf-8")
    cfg = load_config(p)
    assert (cfg.warn_pct, cfg.danger_pct) == (60, 80)


def test_the_slider_gap_is_the_slider_step():
    """5단위 스냅과 5%p 간격이 같은 값이어야 슬라이더가 자기 한계에 정확히 선다.
    두 상수로 갈라두면 한쪽만 고쳐졌을 때 손잡이가 한 칸 못 가거나 넘어간다."""
    assert config.PCT_STEP == 5
    assert config.PCT_MIN < config.PCT_MAX
```

- [ ] **Step 2: 테스트를 돌려 실패 확인**

```bash
python -m pytest tests/test_config.py -v
```

예상: `test_overlay_detailed_*` 넷과 `test_ui_owned_is_gone`,
`test_warn_above_danger_is_corrected_on_load`가 FAIL.

- [ ] **Step 3: `config.py`를 고친다**

13행 아래에 상수를 추가한다.

```python
# 사용률 임계값의 단위. 설정창 슬라이더가 이 값으로 스냅하고, 노란·빨간이
# 서로에게서 이만큼 떨어져 선다. **두 용도가 같은 상수여야 한다** — 갈라두면
# 한쪽만 고쳐졌을 때 손잡이가 자기 한계에 정확히 서지 못한다.
PCT_STEP = 5
PCT_MIN, PCT_MAX = 50, 100
```

`Config`에 필드를 추가한다 (24행 뒤).

```python
    overlay_visible: bool = True
    # 기본값 false가 기본 모드(66×66)와 일치한다. 파일을 열어본 사람이
    # true를 기본으로 보면 지금 보이는 창과 어긋나 헷갈린다.
    overlay_detailed: bool = False
```

`_TYPES`에 짝을 추가한다.

```python
    "overlay_visible": bool,
    "overlay_detailed": bool,
```

37-39행의 `UI_OWNED` 상수와 주석을 삭제한다.

`load_config`의 반환 직전(81행 뒤)에 보정을 넣는다.

```python
    cfg.poll_seconds = max(MIN_POLL_SECONDS, cfg.poll_seconds)
    # warn ≥ danger면 노란색이 영영 안 나온다. 설정창에서만 보정하면 창을 한 번도
    # 안 연 사람은 그대로 남으므로, poll_seconds의 하한을 거는 것과 같은 자리에서
    # 바로잡는다 (스펙 4.1절).
    #
    # **danger를 기준으로 두고 warn을 내린다.** 둘 중 결과가 무거운 쪽이 danger라
    # 그쪽을 사용자 뜻으로 존중한다. 음수까지 내려가지는 않게 0에서 멈춘다.
    if cfg.warn_pct >= cfg.danger_pct:
        cfg.warn_pct = max(0, cfg.danger_pct - PCT_STEP)
    return cfg
```

`save_config`를 전체 쓰기로 단순화한다 (85-109행 전체 교체).

```python
def save_config(cfg: Config, path: Path | None = None) -> None:
    """전체를 쓴다.

    예전에는 디스크 내용 위에 UI가 소유한 값만 덮었다. 근거는 "나머지는 사용자가
    메모장으로 고치는 값"이었는데, 이제 전부 설정창이 소유하므로 그 근거가
    사라졌다. 남는 위험은 프로그램이 켜진 채 파일을 손으로 고치는 경우뿐이고,
    이제 그럴 이유가 없다 — 트레이의 "설정 파일 열기"도 함께 사라졌다.

    임시 파일에 쓰고 바꿔치운다. 반쯤 쓰인 파일이 남으면 다음 기동에서
    전부 기본값으로 떨어진다.
    """
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")
    os.replace(tmp, path)
```

`_coerce`의 독스트링에서 "트레이 메뉴 '설정 파일 열기'로 사용자가 메모장에서
직접 고친다"를 "옛 버전이 남긴 파일이나 손으로 고친 파일이 들어올 수 있다"로
바꾼다. 설정창이 쓴 파일만 들어온다고 가정하면 안 되는 이유는 판올림 전에 쓴
파일이 그대로 남기 때문이다.

- [ ] **Step 4: 테스트를 돌려 통과 확인**

```bash
python -m pytest tests/test_config.py -v
```

예상: 전부 PASS.

- [ ] **Step 5: 전체 테스트로 회귀 확인**

```bash
python -m pytest -q
```

예상: 실패 0.

- [ ] **Step 6: 커밋**

```bash
git add claude_usage_overlay/config.py tests/test_config.py
git commit -m "feat: config를 전체 쓰기로 단순화하고 overlay_detailed 추가"
```

---

## Task 4: text_center — 잉크 중앙 정렬

tkinter가 알려주지 않는 잉크 상자를 PIL로 재고, baseline을 경유해 Tk 좌표로
옮긴다. 근거와 공식은 이 문서 위쪽 "왜 잉크 상자를 PIL로 재는가"에 있다.

**파일:**
- 생성: `claude_usage_overlay/text_center.py`
- 테스트: `tests/test_text_center.py`

**인터페이스:**
- 사용: `font_install.font_file_for(family, bold) -> Path | None` (Task 1)
- 제공:
  - `text_center.Ink` — frozen dataclass, 필드 `left: int` · `right: int` · `top: int` · `bottom: int`. left·right는 펜 시작점 기준, top·bottom은 **baseline 기준**(top은 음수)
  - `text_center.measure_ink(font_path: Path, px: int, text: str) -> Ink | None`
  - `text_center.nw_xy(box: tuple[int, int, int, int], ink: Ink, ascent: int) -> tuple[int, int]`
  - `text_center.center_start(box_size: int, ink_size: int) -> int`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_text_center.py`:

```python
"""잉크 중앙 정렬. 창을 띄우지 않고 재는 것들이다.

Tk 인스턴스가 필요한 것은 ascent 하나뿐이고, 나머지는 PIL과 순수 산수다.
"""

import tkinter as tk
import tkinter.font as tkfont

import pytest

from claude_usage_overlay import text_center
from claude_usage_overlay.font_install import font_file_for
from claude_usage_overlay.text_center import Ink, center_start, measure_ink, nw_xy


@pytest.fixture(scope="module")
def root():
    r = tk.Tk()
    r.withdraw()
    yield r
    r.destroy()


def test_the_spare_half_pixel_goes_up():
    """40px 상자에 13px 잉크를 넣으면 위 13 · 아래 14다. 아래로 보내면 처져 보인다
    (스펙 2.6절 육안 확인)."""
    assert center_start(40, 13) == 13


def test_center_start_uses_floor_not_bankers_rounding():
    """파이썬 round()는 은행가 반올림이라 round(1.5)=2(아래)·round(2.5)=2(위)로
    값의 홀짝에 따라 방향이 갈린다. floor여야 항상 위로 간다."""
    for box, ink in ((40, 13), (40, 11), (33, 12), (33, 10), (48, 21)):
        spare = box - ink
        start = center_start(box, ink)
        assert start == spare // 2
        assert spare - start >= start, f"({box}, {ink}) — 아래 여백이 더 커야 한다"


def test_margins_never_differ_by_more_than_a_pixel():
    for box in range(20, 60):
        for ink in range(5, box):
            start = center_start(box, ink)
            assert abs((box - ink - start) - start) <= 1


def test_measure_ink_is_relative_to_the_baseline():
    """숫자는 baseline에 붙어 있으므로 bottom이 0이다. top은 음수(위쪽)다."""
    ink = measure_ink(font_file_for("Pretendard", bold=True), 18, "100")
    assert ink is not None
    assert ink.bottom == 0
    assert ink.top == -13, "스펙 2.6절: 18px 숫자의 잉크는 13px"


def test_measure_ink_gives_up_on_a_missing_file(tmp_path):
    assert measure_ink(tmp_path / "nope.ttf", 18, "100") is None


def test_nw_xy_reproduces_the_measured_ink_position(root):
    """스펙 2.6절이 화면을 캡처해 픽셀을 센 결과와 맞는지 본다.

    Pretendard 18px `100`, 링 안쪽 상자 top=13 · 높이 40에서 잉크가 26~38을
    덮었고 위 여백 13 · 아래 여백 14였다.
    """
    font = tkfont.Font(root=root, family="Pretendard", size=-18, weight="bold")
    if font.actual("family").lower() != "pretendard":
        pytest.skip("Pretendard가 이 프로세스에 올라와 있지 않다")

    ink = measure_ink(font_file_for("Pretendard", bold=True), 18, "100")
    _x, y = nw_xy((13, 13, 53, 53), ink, font.metrics("ascent"))

    ink_top = y + font.metrics("ascent") + ink.top
    ink_bottom = y + font.metrics("ascent") + ink.bottom
    assert (ink_top, ink_bottom) == (26, 39)      # 픽셀 26~38을 덮는다
    assert (ink_top - 13, 52 - (ink_bottom - 1)) == (13, 14)


@pytest.mark.parametrize("scale", (1.0, 1.25, 1.5))
@pytest.mark.parametrize("text", ("62", "100", "5:20", "0:27", "10:14"))
def test_ink_is_centered_at_every_scale(root, scale, text):
    """스펙 14장이 실측하지 않은 채로 남긴 축이다. 잉크를 매번 재는 방식이므로
    맞을 것으로 봤지만 확인이 필요하다고 적혀 있었다 — 여기서 확인한다.

    위·아래 여백 차이가 1px 이하이고 남는 반 픽셀이 **위로** 간다.
    """
    box_top = round(13 * scale)
    box_size = round(40 * scale)
    px = round(18 * scale)
    path = font_file_for("Pretendard", bold=True)
    font = tkfont.Font(root=root, family="Pretendard", size=-px, weight="bold")
    if font.actual("family").lower() != "pretendard":
        pytest.skip("Pretendard가 이 프로세스에 올라와 있지 않다")

    ink = measure_ink(path, px, text)
    _x, y = nw_xy((box_top, box_top, box_top + box_size, box_top + box_size), ink,
                  font.metrics("ascent"))
    ink_top = y + font.metrics("ascent") + ink.top
    ink_h = ink.bottom - ink.top

    above = ink_top - box_top
    below = box_size - ink_h - above
    assert abs(above - below) <= 1, f"위 {above} / 아래 {below}"
    assert above <= below, "남는 반 픽셀은 위로 보낸다"


def test_a_glyph_off_the_baseline_is_still_centered():
    """`—`는 baseline 위에 떠 있다. resets_at이 없을 때 링 안에 오는 문구다.
    baseline만 맞추면 처져 보이므로 잉크로 맞춰야 한다."""
    ink = Ink(left=0, right=20, top=-12, bottom=-6)
    _x, y = nw_xy((0, 0, 40, 40), ink, 20)
    ink_top = y + 20 + ink.top
    assert ink_top == center_start(40, 6)
```

- [ ] **Step 2: 테스트를 돌려 실패 확인**

```bash
python -m pytest tests/test_text_center.py -v
```

예상: `ModuleNotFoundError: No module named 'claude_usage_overlay.text_center'`.

- [ ] **Step 3: `text_center.py` 작성**

```python
"""잉크 상자를 재서 상자 중앙에 놓는 좌표 계산.

**tkinter는 문자열의 잉크 상자를 알려주지 않는다.** Font.metrics()에는
ascent·descent·linespace만 있고, Canvas.bbox()가 돌려주는 것은 잉크가 아니라
**레이아웃 상자**다. 그래서 잉크는 PIL로 같은 글꼴 파일을 열어 재고, Tk 좌표로는
baseline을 경유해서 옮긴다.

**ascender선을 경유하면 안 된다.** Tk와 PIL이 ascent를 다르게 센다 (실측:
Pretendard Bold 18px에서 Tk 17 · PIL 18, Segoe UI Bold 15px에서 Tk 16 · PIL 17).
잉크 위치를 ascender선 기준으로 넘기면 이 1px이 그대로 어긋난다. baseline 기준
값은 글꼴 파일 자체의 성질이라 양쪽이 같다.

**icon_render._centered_text를 베끼면 안 된다.** 잉크 상자를 매번 재는 것은
맞지만 좌표를 round()로 맞추고 있고, 파이썬의 round()는 은행가 반올림이라
절반은 아래로 간다 — round(1.5)=2(아래), round(2.5)=2(위), round(0.5)=0(위).
값의 홀짝에 따라 방향이 갈리므로 "남는 반 픽셀은 위로"가 지켜지지 않는다.
여기서는 //(floor)로 명시한다.

이 공식은 스펙 2.6절이 화면을 캡처해 픽셀을 센 결과를 그대로 재현한다 —
Pretendard 18px `100`, 링 안쪽 top=13·높이 40에서 잉크 26~38, 위 13 · 아래 14.
"""

from dataclasses import dataclass
from pathlib import Path

from PIL import ImageFont


@dataclass(frozen=True)
class Ink:
    """실제로 칠해지는 상자.

    left·right는 펜 시작점 기준, top·bottom은 **baseline 기준**이다.
    baseline 위가 음수이므로 숫자는 top이 음수이고 bottom이 0이다.
    """

    left: int
    right: int
    top: int
    bottom: int


def measure_ink(font_path: Path | None, px: int, text: str) -> Ink | None:
    """글꼴 파일을 열어 잉크 상자를 잰다. 못 열면 None.

    None을 돌려주는 것은 실패가 아니라 정상 경로다. 부르는 쪽은 그때 잉크 정렬을
    포기하고 레이아웃 상자 중앙에 놓으면 된다 — 1px 어긋날 뿐 화면은 정상이다.
    """
    if font_path is None:
        return None
    try:
        font = ImageFont.truetype(str(font_path), px)
    except (OSError, ValueError):
        return None
    ascent, _descent = font.getmetrics()
    try:
        left, top, right, bottom = font.getbbox(text)
    except (OSError, ValueError):
        return None
    # PIL 기본 anchor는 "la"(left-ascender)라 y=0이 ascender선이다.
    # baseline은 그로부터 ascent 아래에 있으므로 빼서 baseline 기준으로 옮긴다.
    return Ink(int(left), int(right), int(top) - ascent, int(bottom) - ascent)


def center_start(box_size: int, ink_size: int) -> int:
    """상자 안에서 잉크가 시작할 위치. 남는 반 픽셀은 **앞쪽(위·왼쪽)으로.**

    //는 floor다. round()로 하면 은행가 반올림이라 방향이 갈린다 (머리말).
    """
    return (box_size - ink_size) // 2


def nw_xy(box: tuple[int, int, int, int], ink: Ink, ascent: int) -> tuple[int, int]:
    """create_text(anchor="nw")에 넘길 좌표.

    box는 (x0, y0, x1, y1)이고 폭은 x1 - x0다. ascent는 **Tk의** 값이다 —
    anchor="nw"로 그리면 레이아웃 상자 위쪽이 y에 놓이고 baseline은 y + ascent다.
    """
    x0, y0, x1, y1 = box
    x = x0 + center_start(x1 - x0, ink.right - ink.left) - ink.left
    y = y0 + center_start(y1 - y0, ink.bottom - ink.top) - ascent - ink.top
    return x, y
```

- [ ] **Step 4: 테스트를 돌려 통과 확인**

```bash
python -m pytest tests/test_text_center.py -v
```

예상: 전부 PASS. Pretendard가 이 프로세스에 안 올라와 있으면 Tk가 필요한 셋만
skip되고 나머지는 통과한다. **skip이 나오면** `python -c "from claude_usage_overlay import font_install; print(font_install.activate())"`
가 2를 돌려주는지 확인한다 — 0이면 Task 1 Step 1이 덜 됐다.

- [ ] **Step 5: 커밋**

```bash
git add claude_usage_overlay/text_center.py tests/test_text_center.py
git commit -m "feat: baseline 기준 잉크 상자로 중앙 정렬하는 text_center 추가"
```

---

## Task 5: 오버레이 두 모드와 갱신 지연

기본 66×66과 자세히 190×62. 모드를 바꿀 때 오른쪽 아래 모서리를 고정하고
작업 영역 안으로 되민다. 갱신이 한 주기를 통째로 건너뛰면 두 모드 모두 링 채움과
숫자를 지우고 흐린 `!` 하나만 그린다.

**파일:**
- 수정: `claude_usage_overlay/overlay.py` (전면)
- 테스트: `tests/test_overlay_modes.py` (신규), `tests/test_overlay_layout.py` (기본 모드 몫 추가)

**인터페이스:**
- 사용: `text_center.measure_ink` · `text_center.nw_xy` (Task 4), `font_install.font_file_for` (Task 1), `config.Config.overlay_detailed` (Task 3)
- 제공:
  - `overlay.SMALL_SIZE: int = 66` · `SMALL_RING_BOX` · `SMALL_RING_WIDTH` · `SMALL_FONT_PCT_PX = 18` · `SMALL_FONT_TIME_PX = 15` · `MIN_RING_FONT_PX = 8` · `GAP_PADDING_SECONDS = 60`
  - `overlay.BASE_WIDTH` · `BASE_HEIGHT` · `BASE_RING_BOX` · `BASE_RING_WIDTH` · `BASE_TEXT_X` · `BASE_RIGHT_MARGIN` · `BASE_FONT_LINE1_PX` · `BASE_FONT_LINE2_PX` · `BASE_FONT_PCT_PX` · `PCT_INNER_MARGIN` (이름·값 그대로. 자세히 모드 전용 근거가 된다)
  - `overlay.is_refresh_gap(fetched_at: datetime, now: datetime, poll_seconds: int) -> bool`
  - `overlay.resized_position(x: int, y: int, old_size: tuple[int, int], new_size: tuple[int, int], area: tuple[int, int, int, int]) -> tuple[int, int]`
  - `overlay.ring_inner_box(ring_box, ring_width, scale) -> tuple[int, int, int, int]`
  - `overlay.ring_text_limit(ring_box, ring_width, scale) -> int`
  - `overlay.ring_symbol(state: HudState, now: datetime, poll_seconds: int) -> tuple[str, str] | None`
  - `Overlay.set_detailed(detailed: bool) -> None` · `Overlay.is_detailed() -> bool` · `Overlay.schedule(fn) -> None` · `Overlay.apply_config() -> None`
  - `Overlay.update` · `show` · `hide` · `is_visible` (그대로)

- [ ] **Step 1: 실패하는 테스트 작성 — `tests/test_overlay_modes.py`**

```python
"""기본 모드 · 갱신 지연 · 모드 전환 위치. 전부 창 없이 재는 순수 함수다."""

from datetime import datetime, timedelta, timezone

import pytest

from claude_usage_overlay import theme
from claude_usage_overlay import overlay as ov
from claude_usage_overlay.models import HudState, Status, UsageSnapshot

NOW = datetime(2026, 8, 11, 3, 0, tzinfo=timezone.utc)
POLL = 300


def _at(seconds):
    return NOW + timedelta(seconds=seconds)


def _state(status=Status.OK, pct=62.0, fetched=NOW, resets=None):
    return HudState(status, UsageSnapshot(pct, resets, None, fetched), "")


# --- 갱신 지연 임계 (스펙 3.1절) ---


def test_one_missed_tick_keeps_the_number():
    """poller._handle_transient()의 첫 백오프가 poll_seconds라 첫 실패 뒤 다음
    시도는 성공 시점 + 600초다. 그때까지 숫자가 남아 있어야 한다."""
    assert not ov.is_refresh_gap(NOW, _at(POLL), POLL)
    assert not ov.is_refresh_gap(NOW, _at(POLL * 2), POLL)


def test_two_missed_ticks_erase_the_number():
    """낡은 숫자는 없느니만 못하다. 한 주기를 통째로 건너뛰면 지운다."""
    assert ov.is_refresh_gap(NOW, _at(POLL * 2 + 61), POLL)


def test_the_boundary_is_two_periods_plus_a_minute():
    """60초는 분 반올림 경계에서 깜빡이지 않게 더한 것이다."""
    assert not ov.is_refresh_gap(NOW, _at(660), POLL)
    assert ov.is_refresh_gap(NOW, _at(661), POLL)


def test_a_single_auth_race_does_not_erase_anything():
    """_handle_unauthorized()는 백오프를 태우지 않아 다음 시도가 poll_seconds
    뒤다. 한 번의 401로 지우면 기본 5분 주기에서 4분 내내 빈 링이 된다."""
    assert not ov.is_refresh_gap(NOW, _at(POLL), POLL)


def test_the_threshold_follows_the_configured_period():
    """2분 주기로 줄여둔 사람에게 11분을 기다리게 하면 안 된다."""
    assert ov.is_refresh_gap(NOW, _at(361), 120)
    assert not ov.is_refresh_gap(NOW, _at(300), 120)


# --- 링 안에 그릴 것 (스펙 3.1절) ---


def test_relogin_is_a_loud_bang():
    """사용자가 조치해야 하는 것은 또렷하게."""
    assert ov.ring_symbol(HudState(Status.RELOGIN, None, "x"), NOW, POLL) == (
        "!", theme.RED,
    )


def test_a_schema_change_is_a_question_mark():
    assert ov.ring_symbol(HudState(Status.SCHEMA_ERROR, None, "x"), NOW, POLL) == (
        "?", theme.TEXT_LIGHT,
    )


def test_no_value_yet_is_an_ellipsis():
    """첫 조회 전이다. 여기서 `?`를 쓰면 켤 때마다 몇 초 동안 형식 변경 기호가 뜬다."""
    symbol, color = ov.ring_symbol(HudState(Status.STALE, None, "x"), NOW, POLL)
    assert (symbol, color) == (ov.RING_LOADING, theme.TEXT_DIM)


def test_a_refresh_gap_is_a_dim_bang():
    """`!`가 두 뜻을 갖지만 밝기로 갈린다 — 기다리면 낫는 것은 흐리게."""
    state = _state(Status.STALE, fetched=NOW)
    assert ov.ring_symbol(state, _at(661), POLL) == ("!", theme.TEXT_DIM_RING)


def test_a_fresh_value_draws_a_number_not_a_symbol():
    assert ov.ring_symbol(_state(), NOW, POLL) is None


def test_a_stale_but_recent_value_still_draws_the_number():
    """값이 낡았지만 아직 주기 안이면 통째로 흐리게만 그린다. 지우지 않는다."""
    assert ov.ring_symbol(_state(Status.STALE), _at(POLL), POLL) is None


def test_rate_limited_follows_the_same_rule_as_stale():
    """둘 다 '기다리면 낫는다'다. 429 벌칙이 길어지면 함께 지워져야 한다."""
    assert ov.ring_symbol(_state(Status.RATE_LIMITED), _at(POLL), POLL) is None
    assert ov.ring_symbol(_state(Status.RATE_LIMITED), _at(661), POLL) == (
        "!", theme.TEXT_DIM_RING,
    )


# --- 모드를 바꿀 때의 창 위치 (스펙 3.4절) ---

AREA = (0, 0, 1920, 1040)
SMALL, DETAIL = (66, 66), (190, 62)


def test_the_bottom_right_corner_stays_put():
    """기본 위치가 작업 영역 오른쪽 아래이므로 그래야 제자리에 남는다."""
    x, y = ov.resized_position(1830, 950, SMALL, DETAIL, AREA)
    assert (x + DETAIL[0], y + DETAIL[1]) == (1830 + 66, 950 + 66)


def test_shrinking_keeps_the_right_edge_too():
    x, y = ov.resized_position(1706, 916, DETAIL, SMALL, AREA)
    assert (x + SMALL[0], y + SMALL[1]) == (1706 + 190, 916 + 62)


def test_growing_at_the_left_edge_is_pushed_back_inside():
    """왼쪽 끝에 붙여둔 상태에서 자세히로 바꾸면 왼쪽으로 124px 자란다."""
    x, _y = ov.resized_position(0, 500, SMALL, DETAIL, AREA)
    assert x == 0


def test_the_window_never_hangs_off_the_bottom():
    x, y = ov.resized_position(100, 1030, SMALL, DETAIL, AREA)
    assert y + DETAIL[1] <= AREA[3]


def test_a_taskbar_on_top_is_respected():
    """작업 표시줄이 위에 있으면 작업 영역의 top이 0이 아니다."""
    area = (0, 48, 1920, 1080)
    _x, y = ov.resized_position(100, 50, SMALL, DETAIL, area)
    assert y >= 48


# --- 링 기하 (스펙 2.5절 · 3.1절) ---


def test_the_basic_ring_leaves_thirty_two_pixels_for_text():
    """바깥 지름 50 · 두께 5 → 안쪽 40. 링 선과 글자 사이 4px씩 남기면 32px."""
    assert ov.ring_text_limit(ov.SMALL_RING_BOX, ov.SMALL_RING_WIDTH, 1.0) == 32


def test_the_basic_ring_inner_box_is_forty_pixels():
    box = ov.ring_inner_box(ov.SMALL_RING_BOX, ov.SMALL_RING_WIDTH, 1.0)
    assert box == (13, 13, 53, 53)


def test_the_basic_window_is_a_square_with_an_eight_pixel_margin():
    assert ov.SMALL_RING_BOX == (8, 8, ov.SMALL_SIZE - 8, ov.SMALL_SIZE - 8)


@pytest.mark.parametrize("scale", (1.0, 1.25, 1.5))
def test_the_geometry_helpers_agree_at_every_scale(scale):
    """테스트가 코드와 **같은 산수**를 써야 한다. round(32 × 배율)로 어림하면
    125%에서 1px 어긋나 통과해야 할 것이 떨어지거나 반대가 된다."""
    box = ov.ring_inner_box(ov.SMALL_RING_BOX, ov.SMALL_RING_WIDTH, scale)
    limit = ov.ring_text_limit(ov.SMALL_RING_BOX, ov.SMALL_RING_WIDTH, scale)
    margin = round(ov.PCT_INNER_MARGIN * scale)
    assert (box[2] - box[0]) - 2 * margin == limit
```

- [ ] **Step 2: 테스트를 돌려 실패 확인**

```bash
python -m pytest tests/test_overlay_modes.py -v
```

예상: `AttributeError: module 'claude_usage_overlay.overlay' has no attribute 'is_refresh_gap'`.

- [ ] **Step 3: `overlay.py`의 머리말·상수·순수 함수를 고친다**

파일 머리말(1-8행)을 바꾼다.

```python
"""tkinter 오버레이 창.

1초마다 다시 그리지만 네트워크는 부르지 않는다. 카운트다운은
resets_at에서 로컬로 계산한다. 화면은 매초 살아 움직이고 API는 5분에 한 번만.

**모드가 둘이다.**

    기본     66 × 66. 링 하나에 숫자 하나. 평소에 덜 거슬리게
    자세히   190 × 62. 링 + 카운트다운 + 갱신 문구 두 줄 (예전 모습 그대로)

모든 픽셀 치수는 기준값 × DPI 배율이다. 배율 150% PC에서도 같은 크기로 보인다.
글꼴만 규칙이 다르다 — fonts_for()의 주석을 보라.
"""
```

import에 셋을 더한다.

```python
from . import font_install, text_center, theme
from .icon_render import LOADING_TEXT as RING_LOADING
```

`RING_LOADING`을 `icon_render`에서 **가져온다.** 값이 `"…"` 하나뿐이라 베끼기
쉽지만, 트레이 아이콘과 오버레이가 같은 상태를 다른 기호로 말하면 사용자가
둘을 대조할 수 없다.

43-62행의 상수 블록을 아래로 바꾼다. `BASE_*`는 이름과 값이 그대로 남는다 —
`tests/test_overlay_layout.py`가 참조하고, 이제 그것은 **자세히 모드 전용
근거**다.

```python
BASE_WIDTH, BASE_HEIGHT = 190, 62
BASE_RING_BOX = (12, 12, 54, 54)   # x0, y0, x1, y1
BASE_RING_WIDTH = 5
BASE_TEXT_X = 66
BASE_LINE1_Y, BASE_LINE2_Y = 24, 40
BASE_RIGHT_MARGIN = 10
MARGIN = 24
ALPHA = 0.82

# 기본 모드 — 정사각형. 링 하나에 숫자 하나.
#
# 바깥 지름 50px에 여백 8px, 두께 5px이므로 안쪽 지름이 40px이다. 자세히 모드의
# 링(안쪽 32px)보다 크므로 시작 글꼴도 그만큼 크다.
SMALL_SIZE = 66
SMALL_RING_BOX = (8, 8, 58, 58)
SMALL_RING_WIDTH = 5

# 글꼴 크기는 픽셀이다. 음수로 넘긴다 (Tk 규약: 음수 = 픽셀, 양수 = 포인트).
#
# **문구마다 시작 크기를 따로 고른다.** 같은 크기로 `100`과 `5:20`을 둘 다 담으려면
# 15px인데(실측), 그러면 평소 보는 숫자가 작아진다.
SMALL_FONT_PCT_PX = 18
SMALL_FONT_TIME_PX = 15

# 자세히 모드의 링은 안쪽이 32px뿐이다. 꽉 채우면 숫자가 링 선에 닿아 답답해 보인다.
BASE_FONT_PCT_PX = 16
PCT_INNER_MARGIN = 4   # 링 선과 글자 사이에 남기는 여백
BASE_FONT_LINE1_PX = 12
BASE_FONT_LINE2_PX = 11

MIN_RING_FONT_PX = 8   # 이 아래로는 줄이지 않는다. 넘치는 편이 낫다

# 갱신 지연 임계에 더하는 여유. 분 반올림 경계에서 깜빡이지 않게 한다.
GAP_PADDING_SECONDS = 60
```

`DIM_STATUSES` 정의(75행) 뒤에 순수 함수 다섯을 추가한다.

```python
def is_refresh_gap(fetched_at: datetime, now: datetime, poll_seconds: int) -> bool:
    """갱신이 한 주기를 통째로 건너뛰었는지.

    참이면 링 채움과 숫자를 지우고 흐린 `!` 하나만 그린다. 낡은 숫자는 없느니만
    못하고, 숫자를 못 믿으면 링도 못 믿는다.

    **한 번의 실패로 지우면 안 된다.** poller._handle_unauthorized()의 401 경합은
    백오프 없이 다음 틱에 저절로 낫는데, poll_seconds + 60을 기준으로 삼으면 그
    회복을 기다리는 동안(기본 5분 주기에서 4분) 내내 숫자가 사라진다. 두 번
    연속 실패해야, 즉 한 주기를 통째로 건너뛰어야 지운다. 세 번이면 그건 경합이
    아니라 인증 문제라 poller가 Status.RELOGIN으로 넘겨 또렷한 `!`가 된다.
    """
    return (now - fetched_at).total_seconds() > poll_seconds * 2 + GAP_PADDING_SECONDS


def ring_symbol(state: HudState, now: datetime, poll_seconds: int) -> tuple[str, str] | None:
    """링 안에 숫자 대신 기호를 그려야 하면 (기호, 색), 아니면 None.

    어휘는 icon_render의 것을 그대로 쓴다. `!`가 두 뜻을 갖지만 밝기로 갈린다 —
    **기다리면 낫는 것은 흐리게, 사용자가 조치해야 하는 것은 또렷하게.**
    """
    if state.status is Status.RELOGIN:
        return "!", theme.RED
    if state.status is Status.SCHEMA_ERROR:
        return "?", theme.TEXT_LIGHT
    if state.snapshot is None:
        # 첫 조회 전이거나 한 번도 성공하지 못했다. 여기서 `?`를 쓰면 프로그램을
        # 켤 때마다 몇 초 동안 "데이터 형식이 바뀜" 기호가 뜬다.
        return RING_LOADING, theme.TEXT_DIM
    if state.status in DIM_STATUSES and is_refresh_gap(
        state.snapshot.fetched_at, now, poll_seconds
    ):
        return "!", theme.TEXT_DIM_RING
    return None


def ring_inner_box(
    ring_box: tuple[int, int, int, int], ring_width: int, scale: float
) -> tuple[int, int, int, int]:
    """링 안쪽 원이 차지하는 상자. 글자를 중앙에 놓는 기준이다."""
    x0, y0, x1, y1 = (round(v * scale) for v in ring_box)
    rw = max(3, round(ring_width * scale))
    return (x0 + rw, y0 + rw, x1 - rw, y1 - rw)


def ring_text_limit(
    ring_box: tuple[int, int, int, int], ring_width: int, scale: float
) -> int:
    """링 안에 글자가 들어가야 하는 폭.

    계산을 함수로 빼는 이유는 테스트가 코드와 **같은 산수**를 써야 하기 때문이다 —
    round(32 × 배율)로 어림하면 125%에서 1px 어긋나 통과해야 할 것이 떨어지거나
    반대가 된다.
    """
    x0, _y0, x1, _y1 = ring_inner_box(ring_box, ring_width, scale)
    return (x1 - x0) - 2 * round(PCT_INNER_MARGIN * scale)


def resized_position(
    x: int,
    y: int,
    old_size: tuple[int, int],
    new_size: tuple[int, int],
    area: tuple[int, int, int, int],
) -> tuple[int, int]:
    """창 크기가 바뀔 때의 새 좌표. **오른쪽 아래 모서리를 고정한다.**

    기본 위치가 작업 영역 오른쪽 아래이므로 그래야 제자리에 남는다.

    **옮겨둔 자리에서는 작업 영역 안으로 되민다.** 창은 드래그로 어디든 갈 수
    있고, 왼쪽 끝에 붙여둔 상태에서 자세히로 바꾸면 오른쪽 아래를 고정한 채
    왼쪽으로 124px 자라 화면 밖으로 나간다.

    예전에 16d1eba가 폭 변경에 대해 같은 보정을 넣은 적이 있으나, 위치 저장
    기능을 통째로 되돌린 62a2fa4가 함께 지웠다. 새로 만드는 부분이다.
    """
    old_w, old_h = old_size
    new_w, new_h = new_size
    left, top, right, bottom = area
    nx = max(left, min(x + old_w - new_w, right - new_w))
    ny = max(top, min(y + old_h - new_h, bottom - new_h))
    return nx, ny
```

- [ ] **Step 4: 순수 함수만 먼저 통과 확인**

```bash
python -m pytest tests/test_overlay_modes.py -v
```

예상: 전부 PASS. 클래스는 아직 안 고쳤지만 이 테스트는 순수 함수만 본다.

- [ ] **Step 5: 커밋 (중간 저장)**

```bash
git add claude_usage_overlay/overlay.py tests/test_overlay_modes.py
git commit -m "feat: 오버레이 갱신 지연 임계와 모드 전환 위치 계산 추가"
```

- [ ] **Step 6: `_Geometry`를 추가하고 `Overlay.__init__`을 고친다**

`class Overlay` 바로 앞에 넣는다.

```python
class _Geometry:
    """한 모드의 치수. 배율을 곱한 실제 픽셀이다.

    두 모드가 링 크기까지 다르므로 치수를 인스턴스 속성으로 흩어 두면 모드를
    바꿀 때 어느 것을 다시 계산해야 하는지 매번 세게 된다. 묶어서 통째로 갈아끼운다.
    """

    def __init__(self, scale: float, w: int, h: int, ring_box, ring_width: int) -> None:
        self.w = round(w * scale)
        self.h = round(h * scale)
        self.ring = tuple(round(v * scale) for v in ring_box)
        self.ring_width = max(3, round(ring_width * scale))
        self.inner = ring_inner_box(ring_box, ring_width, scale)
        self.text_limit = ring_text_limit(ring_box, ring_width, scale)

    def size(self) -> tuple[int, int]:
        return (self.w, self.h)
```

`__init__`의 114-166행을 아래로 바꾼다.

```python
    def __init__(self, root: tk.Tk, config: Config) -> None:
        self._root = root
        self._config = config
        self._scale = dpi_scale()
        self._family = pick_font_family(root)
        # 잉크 상자를 재려면 패밀리 이름이 아니라 파일이 필요하다 (text_center 머리말).
        # 못 찾으면 None이고, 그때는 레이아웃 상자 중앙에 놓는다.
        self._font_path = font_install.font_file_for(self._family, bold=True)

        s = self._scale
        self._small = _Geometry(s, SMALL_SIZE, SMALL_SIZE, SMALL_RING_BOX, SMALL_RING_WIDTH)
        self._detail = _Geometry(s, BASE_WIDTH, BASE_HEIGHT, BASE_RING_BOX, BASE_RING_WIDTH)
        self._detailed = config.overlay_detailed

        self._text_x = round(BASE_TEXT_X * s)
        self._line1_y = round(BASE_LINE1_Y * s)
        self._line2_y = round(BASE_LINE2_Y * s)
        fonts = fonts_for(s, self._family)
        self._font_line1 = fonts["line1"]
        self._font_line2 = fonts["line2"]

        self._win = tk.Toplevel(root)
        self._win.overrideredirect(True)          # 테두리 제거
        self._win.attributes("-topmost", True)    # 항상 위
        self._win.attributes("-alpha", ALPHA)     # 반투명
        self._win.configure(bg=theme.BG)

        geo = self._geo()
        x, y = self._initial_position()
        self._win.geometry(f"{geo.w}x{geo.h}+{x}+{y}")

        self._canvas = tk.Canvas(
            self._win, width=geo.w, height=geo.h, bg=theme.BG, highlightthickness=0
        )
        self._canvas.pack()
        self._round_corners()

        # 드래그로 옮길 수 있지만 놓은 자리를 저장하지는 않는다.
        self._drag = {"x": 0, "y": 0}
        for widget in (self._win, self._canvas):
            widget.bind("<Button-1>", self._on_press)
            widget.bind("<B1-Motion>", self._on_drag)

        # 링 그림 캐시. PhotoImage는 참조가 끊기면 화면에서 사라진다.
        self._ring_key: tuple | None = None
        self._ring_photo: ImageTk.PhotoImage | None = None

        # 링 안 글꼴과 잉크 상자 캐시. 문구를 그대로 키로 쓴다 — 자릿수로 묶으면
        # `5:20`처럼 콜론이 섞인 문구가 같은 칸에 들어가 폭이 어긋난다.
        self._fonts: dict[tuple, tuple[tkfont.Font, int]] = {}
        self._inks: dict[tuple, text_center.Ink | None] = {}

        self._state = HudState(Status.STALE, None, LOADING_TEXT)
        self._visible = config.overlay_visible
        if not self._visible:
            self._win.withdraw()
        self._tick()

    def _geo(self) -> _Geometry:
        return self._detail if self._detailed else self._small
```

- [ ] **Step 7: 모드 전환 공개 인터페이스를 추가한다**

`_set_visible` 뒤에 넣는다.

```python
    def is_detailed(self) -> bool:
        """Tk에 묻지 않는다. 메뉴 문구를 그릴 때마다 불리는 함수라
        pystray 스레드에서 Tk를 건드리게 된다."""
        return self._detailed

    def set_detailed(self, detailed: bool) -> None:
        """모드를 바꾼다. **전환 상태는 저장한다** — 스펙 9장이 config 필드로 정했다.

        좌클릭으로 바뀌는 사용량↔남은 시간 표시와는 다르다. 그쪽은 저장하지 않는다.
        """
        if detailed == self._detailed:
            return
        self._detailed = detailed
        self._config.overlay_detailed = detailed
        save_config(self._config)
        self._win.after(0, self._apply_geometry)

    def schedule(self, fn) -> None:
        """콜백을 메인 스레드로 넘긴다. 트레이(pystray 스레드)가 쓴다.

        tkinter 창 조작은 메인 스레드 몫이다. after()는 콜백을 이벤트 큐에 넣을
        뿐이고 실행은 mainloop가 한다.
        """
        self._win.after(0, fn)

    def apply_config(self) -> None:
        """설정창이 닫힌 뒤 표시 여부와 모드를 Config에 맞춘다."""
        self._set_visible(self._config.overlay_visible)
        self.set_detailed(self._config.overlay_detailed)

    def _apply_geometry(self) -> None:
        """창과 캔버스 크기를 지금 모드에 맞추고 위치를 보정한다.

        캐시를 비우는 이유는 링 안쪽 폭이 달라져 **줄이는 루프의 결과가 달라지기**
        때문이다. 안 비우면 자세히 모드에서 고른 16px 글꼴이 기본 모드의 큰 링에
        그대로 쓰여 작게 보인다.
        """
        geo = self._geo()
        x, y = resized_position(
            self._win.winfo_x(),
            self._win.winfo_y(),
            (self._win.winfo_width(), self._win.winfo_height()),
            geo.size(),
            work_area(),
        )
        self._win.geometry(f"{geo.w}x{geo.h}+{x}+{y}")
        self._canvas.configure(width=geo.w, height=geo.h)
        self._ring_key = None
        self._fonts.clear()
        self._redraw()
```

`_initial_position`의 `self._w`·`self._h` 참조를 `self._geo()`로 바꾼다.

```python
        _left, _top, right, bottom = work_area()
        geo = self._geo()
        return right - geo.w - MARGIN, bottom - geo.h - MARGIN
```

- [ ] **Step 8: 그리기를 두 모드로 나눈다**

247-319행(`_redraw`와 `_pct_font`)을 아래로 바꾼다.

```python
    def _redraw(self) -> None:
        self._canvas.delete("all")
        now = datetime.now(timezone.utc)
        if self._detailed:
            self._redraw_detailed(self._state, now)
        else:
            self._redraw_small(self._state, now)

    # --- 기본 모드 -------------------------------------------------------

    def _redraw_small(self, state: HudState, now: datetime) -> None:
        """링 안에 숫자 하나. 값이 없거나 못 믿을 때는 기호 하나."""
        geo = self._small
        symbol = ring_symbol(state, now, self._config.poll_seconds)
        if symbol is not None:
            text, color = symbol
            # 링 채움을 그리지 않는다. 숫자를 못 믿으면 링도 못 믿는다.
            self._draw_ring(geo, 0, theme.RING_DIM if text == "!" else theme.GREY)
            self._draw_ring_text(geo, text, color, SMALL_FONT_PCT_PX)
            return

        snap = state.snapshot
        pct = snap.five_hour_pct
        dim = state.status in DIM_STATUSES
        color = theme.color_for(pct, self._config.warn_pct, self._config.danger_pct)
        self._draw_ring(geo, pct, theme.RING_DIM if dim else color)
        self._draw_ring_text(
            geo,
            str(int(round(pct))),
            theme.TEXT_DIM_RING if dim else theme.TEXT_LIGHT,
            SMALL_FONT_PCT_PX,
        )

    # --- 자세히 모드 -----------------------------------------------------

    def _redraw_detailed(self, state: HudState, now: datetime) -> None:
        geo = self._detail

        if state.status is Status.RELOGIN:
            # 문구는 credentials가 정한다. "제목 — 할 일" 형태를 두 줄로 나눈다.
            head, _, tail = state.detail.partition(" — ")
            self._draw_ring(geo, 0, theme.GREY)
            self._draw_text(head or "재로그인 필요", theme.RED, tail, theme.TEXT_DIM)
            return

        if state.snapshot is None:
            # 첫 조회 전(STALE)과 SCHEMA_ERROR가 모두 여기로 온다. 문구는
            # 만든 쪽이 정하므로 오버레이는 기호를 고를 필요가 없다.
            self._draw_ring(geo, 0, theme.GREY)
            self._draw_text(state.detail or LOADING_TEXT, theme.TEXT_DIM, "", theme.TEXT_DIM)
            return

        snap = state.snapshot
        dim = state.status in DIM_STATUSES
        gap = dim and is_refresh_gap(snap.fetched_at, now, self._config.poll_seconds)

        if gap:
            # 3.1절의 근거("낡은 숫자는 없느니만 못하다")는 창 크기와 무관하다.
            # 한쪽만 지우면 클릭 한 번으로 못 믿을 숫자가 도로 나타난다.
            self._draw_ring(geo, 0, theme.RING_DIM)
            self._draw_ring_text(geo, "!", theme.TEXT_DIM_RING, BASE_FONT_PCT_PX)
        else:
            pct = snap.five_hour_pct
            color = theme.color_for(pct, self._config.warn_pct, self._config.danger_pct)
            self._draw_ring(geo, pct, theme.RING_DIM if dim else color)
            self._draw_ring_text(
                geo,
                str(int(round(pct))),
                theme.TEXT_DIM_RING if dim else theme.TEXT_LIGHT,
                BASE_FONT_PCT_PX,
            )

        # 아래 두 줄은 갱신 지연에서도 흐리게 그대로 둔다 — `N분째 갱신 실패`가
        # 바로 옆에서 상태를 말하고 있으므로 카운트다운까지 지울 이유는 없다.
        line1 = format_countdown(snap.resets_at, now)
        if state.status is Status.STALE:
            line2, line2_color = state.detail, theme.YELLOW
        elif state.status is Status.RATE_LIMITED:
            line2, line2_color = RATE_LIMITED_TEXT, theme.YELLOW
        else:
            line2, line2_color = format_age(snap.fetched_at, now), theme.TEXT_DIM

        self._draw_text(
            line1, theme.TEXT_DIM_RING if dim else theme.TEXT_LIGHT, line2, line2_color
        )

    # --- 링 안 글자 ------------------------------------------------------

    def _draw_ring_text(self, geo: _Geometry, text: str, color: str, start_px: int) -> None:
        font, px = self._ring_font(geo, text, start_px)
        ink = self._ink(px, text)
        if ink is None:
            # 글꼴 파일을 못 찾았다. 잉크 정렬을 포기하고 레이아웃 상자 중앙에
            # 놓는다 — 1px 처져 보일 뿐 화면은 정상이다.
            self._canvas.create_text(
                (geo.inner[0] + geo.inner[2]) / 2,
                (geo.inner[1] + geo.inner[3]) / 2,
                text=text, fill=color, font=font,
            )
            return
        x, y = text_center.nw_xy(geo.inner, ink, font.metrics("ascent"))
        self._canvas.create_text(x, y, text=text, anchor="nw", fill=color, font=font)

    def _ring_font(self, geo: _Geometry, text: str, start_px: int):
        """링 안에 들어가는 가장 큰 글꼴과 그 픽셀 크기.

        **시작 크기를 확정값으로 쓰지 않는다.** 배율 100%에서 여유가 정확히 0px이라
        반올림이 한 번만 어긋나면 넘친다(실측: 125%의 `5:20`은 42px, 150%의 `100`은
        49px로 가용폭을 넘는다). create_text는 넘쳐도 경고 없이 자르므로 상수로
        박아두면 깨진 화면을 아무도 못 본다. 그래서 들어갈 때까지 1px씩 줄인다 —
        이 루프 하나가 배율뿐 아니라 두 자리 시(`10:14`)까지 함께 흡수한다.
        """
        key = (text, start_px, geo.text_limit)
        cached = self._fonts.get(key)
        if cached is not None:
            return cached

        px = round(start_px * self._scale)
        font = tkfont.Font(root=self._win, family=self._family, size=-px, weight="bold")
        while px > MIN_RING_FONT_PX and font.measure(text) > geo.text_limit:
            px -= 1
            font = tkfont.Font(root=self._win, family=self._family, size=-px, weight="bold")

        self._fonts[key] = (font, px)
        return font, px

    def _ink(self, px: int, text: str) -> "text_center.Ink | None":
        key = (text, px)
        if key not in self._inks:
            self._inks[key] = text_center.measure_ink(self._font_path, px, text)
        return self._inks[key]
```

`_draw_ring`과 `_draw_text`가 `self._ring`·`self._ring_width`를 쓰던 것을
`geo`를 받게 바꾼다.

```python
    def _draw_ring(self, geo: _Geometry, pct: float, color: str) -> None:
        """링은 캔버스가 아니라 PIL이 그린다.

        create_arc에는 안티앨리어싱이 없어 곡선이 픽셀 계단으로 드러난다.
        ring_render는 크게 그려 축소하므로 경계가 매끈하다.

        그림은 (크기, 정수 %, 색)이 바뀔 때만 다시 만든다. 크기가 키에 들어 있어
        모드를 바꾸면 자동으로 다시 만들어진다.
        """
        x0, y0, x1, y1 = geo.ring
        key = (x1 - x0, int(round(pct)), color)
        if key != self._ring_key:
            self._ring_photo = ImageTk.PhotoImage(
                render_ring(x1 - x0, pct, color, bg=theme.BG, width=geo.ring_width)
            )
            self._ring_key = key
        self._canvas.create_image(x0, y0, image=self._ring_photo, anchor="nw")
```

`_draw_text`는 그대로 둔다 — 자세히 모드 전용이고 좌표가 `self._text_x` 등이다.

- [ ] **Step 9: 기본 모드 링 폭 테스트를 `test_overlay_layout.py`에 추가**

파일 머리말에 한 줄을 더한다: `**LINE1·LINE2와 창 폭 190px은 자세히 모드 근거다.**`
그리고 `test_ring_number_fits_inside_the_ring` 뒤에 붙인다.

```python
def test_ring_number_fits_in_the_basic_mode_ring(root):
    """기본 모드는 링 안쪽이 40px이라 사용량을 18px로, 남은 시간을 15px로 시작한다.

    배율 셋과 글꼴 둘을 모두 재는 이유는 스펙 2.5절의 실측 때문이다 — 125%의
    `5:20`은 42px, 150%의 `100`은 49px로 가용폭을 넘는다. 줄이는 루프를 거친
    뒤의 크기를 잰다.
    """
    families = {ov.pick_font_family(root), ov.FALLBACK_FAMILY}
    cases = (
        ("62", ov.SMALL_FONT_PCT_PX),
        ("100", ov.SMALL_FONT_PCT_PX),
        ("5:20", ov.SMALL_FONT_TIME_PX),
        ("0:27", ov.SMALL_FONT_TIME_PX),
        ("10:14", ov.SMALL_FONT_TIME_PX),
    )
    for scale in (1.0, 1.25, 1.5):
        limit = ov.ring_text_limit(ov.SMALL_RING_BOX, ov.SMALL_RING_WIDTH, scale)
        for text, start in cases:
            for family in families:
                px = round(start * scale)
                font = tkfont.Font(root=root, family=family, size=-px, weight="bold")
                while px > ov.MIN_RING_FONT_PX and font.measure(text) > limit:
                    px -= 1
                    font = tkfont.Font(root=root, family=family, size=-px, weight="bold")
                assert font.measure(text) <= limit, (text, family, scale)
                assert px > ov.MIN_RING_FONT_PX, (
                    f"{text!r}가 바닥({px}px)까지 줄었다 — 링이 너무 작다"
                )
```

- [ ] **Step 10: 테스트를 돌려 통과 확인**

```bash
python -m pytest tests/test_overlay_modes.py tests/test_overlay_layout.py -v
```

예상: 전부 PASS.

- [ ] **Step 11: 실제로 띄워서 두 모드를 눈으로 확인**

```bash
python -m claude_usage_overlay
```

기본 모드(66×66)로 뜨는지, 링 안 숫자가 위아래 중앙에 있는지 본다. 자세히
모드는 `%APPDATA%\claude-usage-overlay\config.json`의 `overlay_detailed`를
`true`로 고치고 다시 띄워 확인한다 (전환 조작은 Task 13에서 붙는다).

- [ ] **Step 12: 전체 테스트로 회귀 확인**

```bash
python -m pytest -q
```

- [ ] **Step 13: 커밋**

```bash
git add claude_usage_overlay/overlay.py tests/test_overlay_layout.py
git commit -m "feat: 오버레이를 기본 66x66과 자세히 두 모드로 나눔"
```

---

## Task 6: 클릭·드래그 판정과 사용량 ↔ 남은 시간 전환

기본 모드에서 링 안 숫자를 좌클릭하면 사용량 ↔ 남은 시간이 바뀐다. 드래그와
클릭은 3px로 가른다.

**파일:**
- 수정: `claude_usage_overlay/formatting.py` (추가), `claude_usage_overlay/overlay.py` (조작)
- 테스트: `tests/test_formatting.py` (추가), `tests/test_overlay_modes.py` (추가)

**인터페이스:**
- 사용: `overlay.SMALL_FONT_TIME_PX` (Task 5)
- 제공:
  - `formatting.format_ring_time(resets_at: datetime | None, now: datetime) -> str`
  - `overlay.DRAG_THRESHOLD: int = 3`
  - `overlay.is_drag(dx: int, dy: int, threshold: int = DRAG_THRESHOLD) -> bool`

- [ ] **Step 1: 실패하는 테스트 작성 — `tests/test_formatting.py`에 추가**

```python
def test_ring_time_is_hours_and_minutes():
    """링 안은 좁아서 `5시간 20분 후 리셋`이 안 들어간다. `5:20`으로 줄인다."""
    assert format_ring_time(NOW + timedelta(hours=5, minutes=20), NOW) == "5:20"


def test_ring_time_does_not_pad_the_hour():
    """자리를 채우는 0은 붙이지 않는다. `05:27`은 시계로 읽히고 남은 시간이
    아니라 리셋 시각처럼 보인다."""
    assert format_ring_time(NOW + timedelta(minutes=27), NOW) == "0:27"


def test_ring_time_pads_the_minute():
    """분은 채운다. `5:3`은 3분인지 30분인지 읽는 사람이 못 가른다."""
    assert format_ring_time(NOW + timedelta(hours=5, minutes=3), NOW) == "5:03"


def test_ring_time_allows_a_two_digit_hour():
    """5시간 창이니 한 자리일 것 같지만 format_countdown의 최장이
    `10시간 14분 후 리셋`이라 코드는 두 자리를 허용한다. 표기 규칙을 따로 두지
    않는다 — 링 안에서는 글자가 작아질 뿐 잘리지 않는다 (스펙 3.3절)."""
    assert format_ring_time(NOW + timedelta(hours=10, minutes=14), NOW) == "10:14"


def test_ring_time_without_a_reset_is_a_dash():
    """사용량 0인 새 창에서는 resets_at이 null로 온다."""
    assert format_ring_time(None, NOW) == NO_RESET_TEXT


def test_ring_time_never_goes_negative():
    """리셋 시각을 지나쳤는데 다음 조회 전이면 음수 초가 나온다."""
    assert format_ring_time(NOW - timedelta(minutes=5), NOW) == "0:00"
```

`tests/test_formatting.py`는 이미 `timedelta`와 `NOW`를 갖고 있다. import 목록에
`NO_RESET_TEXT`와 `format_ring_time`만 더한다.

```python
from claude_usage_overlay.formatting import (
    NO_RESET_TEXT,
    format_age,
    format_countdown,
    format_ring_time,
    format_stale_detail,
)
```

- [ ] **Step 2: `tests/test_overlay_modes.py`에 3px 판정 테스트 추가**

```python
# --- 드래그와 클릭 (스펙 3.3절) ---


def test_a_small_wobble_is_a_click():
    """단추를 누르는 동안 손이 1~2px 흔들리는 것은 정상이다."""
    assert not ov.is_drag(2, 0)
    assert not ov.is_drag(0, 2)
    assert not ov.is_drag(-2, 2)


def test_moving_past_the_threshold_is_a_drag():
    assert ov.is_drag(4, 0)
    assert ov.is_drag(0, -4)


def test_the_threshold_itself_counts_as_a_drag():
    assert ov.is_drag(3, 0)


def test_a_diagonal_wobble_is_judged_per_axis():
    """유클리드 거리로 재면 (3, 3)이 4.24가 되어 같은 3px 이동이 축에 따라
    갈린다. 축별 최댓값으로 본다."""
    assert ov.is_drag(3, 3)
    assert not ov.is_drag(2, 2)
```

- [ ] **Step 3: 테스트를 돌려 실패 확인**

```bash
python -m pytest tests/test_formatting.py tests/test_overlay_modes.py -v
```

예상: `ImportError: cannot import name 'format_ring_time'`와
`AttributeError: ... has no attribute 'is_drag'`.

- [ ] **Step 4: `formatting.py`에 `format_ring_time`을 추가**

`format_countdown` 뒤에 넣는다.

```python
def format_ring_time(resets_at: datetime | None, now: datetime) -> str:
    """링 안에 넣는 남은 시간. `5:20`(시:분).

    format_countdown과 따로 두는 이유는 들어갈 자리가 다르기 때문이다. 링 안쪽은
    32px뿐이라 `5시간 20분 후 리셋`이 들어가지 않는다.

    **시에는 자리를 채우는 0을 붙이지 않는다.** `05:27`은 시계로 읽혀서 남은
    시간이 아니라 리셋 시각처럼 보인다. 분은 채운다 — `5:3`은 3분인지 30분인지
    읽는 사람이 못 가른다.

    **시가 한 자리라고 가정하지 않는다.** 5시간 창이니 그럴 것 같지만
    format_countdown의 최장이 "10시간 14분 후 리셋"이라 코드는 두 자리를 허용한다.
    링 안에서는 글자가 작아질 뿐 잘리지 않는다 (overlay._ring_font).
    """
    if resets_at is None:
        return NO_RESET_TEXT
    remaining = max(0, int((resets_at - now).total_seconds()))
    hours, minutes = divmod(remaining // 60, 60)
    return f"{hours}:{minutes:02d}"
```

- [ ] **Step 5: `overlay.py`에 판정 함수와 상수를 추가**

`GAP_PADDING_SECONDS` 뒤에 넣는다.

```python
# 드래그와 클릭을 가르는 이동량. **배율을 곱하지 않는다.**
#
# 그려지는 치수가 아니라 손떨림 허용치다. 150% PC에서 4.5px로 늘리면 그 PC의
# 사용자만 클릭이 더 잘 먹는 것이 아니라, 정말 옮기려고 3px 끌었을 때 창이
# 안 따라온다. 마우스가 보내는 픽셀은 배율과 무관하다.
DRAG_THRESHOLD = 3
```

`resized_position` 뒤에 넣는다.

```python
def is_drag(dx: int, dy: int, threshold: int = DRAG_THRESHOLD) -> bool:
    """누른 자리에서 이만큼 움직였으면 이동이다.

    **축별 최댓값으로 본다.** 유클리드 거리로 재면 (3, 3)이 4.24가 되어 같은
    3px 이동이 축에 따라 갈린다.
    """
    return max(abs(dx), abs(dy)) >= threshold
```

- [ ] **Step 6: 조작 처리를 고친다**

`__init__`의 바인딩 블록을 바꾼다.

```python
        # 드래그로 옮길 수 있지만 놓은 자리를 저장하지는 않는다.
        # 뗄 때(<ButtonRelease-1>)를 보는 이유는 클릭과 드래그를 가르기 위해서다.
        self._drag = {"x": 0, "y": 0, "ox": 0, "oy": 0, "moved": False}
        # 링 안에 사용량 대신 남은 시간을 그리는지. **저장하지 않는다** —
        # 창 위치를 저장하지 않는 것과 같은 이유이고, 다시 켜면 사용량으로 돌아온다.
        self._show_time = False
        for widget in (self._win, self._canvas):
            widget.bind("<Button-1>", self._on_press)
            widget.bind("<B1-Motion>", self._on_drag)
            widget.bind("<ButtonRelease-1>", self._on_release)
```

드래그 이동 블록(232-239행)을 바꾼다.

```python
    def _on_press(self, event) -> None:
        self._drag["x"] = event.x_root - self._win.winfo_x()
        self._drag["y"] = event.y_root - self._win.winfo_y()
        self._drag["ox"] = event.x_root
        self._drag["oy"] = event.y_root
        self._drag["moved"] = False

    def _on_drag(self, event) -> None:
        if is_drag(event.x_root - self._drag["ox"], event.y_root - self._drag["oy"]):
            self._drag["moved"] = True
        if not self._drag["moved"]:
            # 아직 클릭일 수 있다. 여기서 창을 움직이면 1px 흔들림에 창이 떨린다.
            return
        self._win.geometry(
            f"+{event.x_root - self._drag['x']}+{event.y_root - self._drag['y']}"
        )

    def _on_release(self, event) -> None:
        """3px 안에서 뗐으면 클릭이다.

        **자세히 모드에는 좌클릭 전환이 없다.** 아래 줄에 이미 카운트다운이 있어서
        같은 값을 두 자리에 보이게 될 뿐이다.
        """
        if self._drag["moved"] or self._detailed:
            return
        self._show_time = not self._show_time
        self._redraw()
```

- [ ] **Step 7: 기본 모드가 두 문구를 그리게 한다**

`_redraw_small`의 숫자 그리는 부분을 바꾼다.

```python
        snap = state.snapshot
        dim = state.status in DIM_STATUSES
        color = theme.color_for(
            snap.five_hour_pct, self._config.warn_pct, self._config.danger_pct
        )
        self._draw_ring(geo, snap.five_hour_pct, theme.RING_DIM if dim else color)

        if self._show_time:
            text, start_px = format_ring_time(snap.resets_at, now), SMALL_FONT_TIME_PX
        else:
            text, start_px = str(int(round(snap.five_hour_pct))), SMALL_FONT_PCT_PX
        self._draw_ring_text(
            geo, text, theme.TEXT_DIM_RING if dim else theme.TEXT_LIGHT, start_px
        )
```

`formatting` import에 `format_ring_time`을 추가한다.

```python
from .formatting import (
    LOADING_TEXT,
    RATE_LIMITED_TEXT,
    format_age,
    format_countdown,
    format_ring_time,
)
```

- [ ] **Step 8: 테스트를 돌려 통과 확인**

```bash
python -m pytest tests/test_formatting.py tests/test_overlay_modes.py -v
```

예상: 전부 PASS.

- [ ] **Step 9: 실제로 눌러서 확인**

```bash
python -m claude_usage_overlay
```

링 안을 클릭하면 숫자 ↔ `5:20`이 바뀌고, 끌면 창이 따라오고, 끌고 나서 뗄 때는
전환이 **안 되는지** 본다. 마지막 것이 3px 판정의 요점이다.

- [ ] **Step 10: 커밋**

```bash
git add claude_usage_overlay/formatting.py claude_usage_overlay/overlay.py tests/test_formatting.py tests/test_overlay_modes.py
git commit -m "feat: 링 안 좌클릭으로 사용량↔남은 시간 전환, 드래그는 3px로 가름"
```

---

## Task 7: tray_promote — 작업 표시줄 아이콘 고정

Windows 11의 `NotifyIconSettings`에서 우리 항목을 찾아 `IsPromoted=1`을 쓴다.
**즉시 반영되지 않는다** — 탐색기가 이 값을 시작할 때 읽고 그 뒤로는 자기
캐시를 쓴다(실측). 그래서 이 기능은 "다음 로그온부터 보이게 만드는" 기능이다.

**파일:**
- 생성: `claude_usage_overlay/tray_promote.py`
- 테스트: `tests/test_tray_promote.py`

**인터페이스:**
- 제공:
  - `tray_promote.NotifyItem` — frozen dataclass, 필드 `key: str` · `tooltip: str` · `exe_path: str` · `promoted: bool`
  - `tray_promote.TOOLTIP_PREFIX: str = "Claude 사용량"`
  - `tray_promote.pick_items(items: list[NotifyItem], exe_name: str) -> list[NotifyItem]`
  - `tray_promote.is_supported() -> bool`
  - `tray_promote.exe_name() -> str`
  - `tray_promote.read_items() -> list[NotifyItem]`
  - `tray_promote.write_promoted(keys: list[str], value: bool) -> bool`
  - `tray_promote.is_promoted(name: str | None = None) -> bool`
  - `tray_promote.promote(value: bool = True, name: str | None = None) -> bool`
  - `tray_promote.promote_when_ready(attempts: int = 10, delay: float = 3.0, sleep=time.sleep, name=None) -> bool`

- [ ] **Step 1: 실패하는 테스트 작성 — `tests/test_tray_promote.py`**

```python
"""레지스트리 항목 목록에서 우리 것을 고르는 판정.

실제 레지스트리 접근은 얇은 껍데기(read_items·write_promoted)로 분리했고,
틀리기 쉬운 것은 51개 항목 중 무엇이 우리 것이냐다 — 실측으로 확인한 세 가지
함정이 여기 들어간다 (스펙 2.8절).
"""

from claude_usage_overlay import tray_promote as tp
from claude_usage_overlay.tray_promote import NotifyItem, pick_items

# 스펙 2.8절의 실측. ExecutablePath는 절대 경로가 아니다 — 시스템 폴더 아래
# 실행 파일은 KNOWNFOLDERID GUID 접두사로 저장된다.
POWERTOYS = NotifyItem(
    key="a1",
    tooltip="",
    exe_path=r"{6D809377-6AF0-444B-8957-A3773F02200E}\PowerToys\PowerToys.exe",
    promoted=True,
)
EXPLORER = NotifyItem(
    key="a2",
    tooltip="",
    exe_path=r"{F38BF404-1D43-42F2-9305-67DE0B28FC23}\explorer.exe",
    promoted=False,
)
CLAUDE_DESKTOP = NotifyItem(
    key="a3", tooltip="", exe_path=r"C:\Users\me\AppData\Local\Claude\Claude.exe",
    promoted=True,
)
OURS_PYTHONW = NotifyItem(
    key="b1",
    tooltip="Claude 사용량\n불러오는 중",
    exe_path=r"C:\Python312\pythonw.exe",
    promoted=False,
)
OURS_EXE = NotifyItem(
    key="b2",
    tooltip="Claude 사용량\n5시간 창  62%  ·  2시간 10분 후 리셋",
    exe_path=r"C:\Users\me\IdeaProjects\CLAUDE_HUD\dist\ClaudeUsageOverlay.exe",
    promoted=False,
)
OTHER_PYTHONW = NotifyItem(
    key="c1", tooltip="다른 파이썬 프로그램", exe_path=r"C:\Python312\pythonw.exe",
    promoted=True,
)

ALL = [POWERTOYS, EXPLORER, CLAUDE_DESKTOP, OURS_PYTHONW, OURS_EXE, OTHER_PYTHONW]


def test_the_tooltip_is_the_primary_condition():
    """ExecutablePath는 절대 경로가 아닐 수 있고, 어긋나면 기능이 아무 표시 없이
    죽는다. 툴팁으로 고르고 경로는 후보를 가리는 데만 쓴다."""
    picked = pick_items(ALL, "ClaudeUsageOverlay.exe")
    assert [i.key for i in picked] == ["b2"]


def test_a_colliding_python_path_is_not_enough():
    """같은 pythonw.exe로 도는 다른 프로그램이 잡히면 남의 아이콘을 꺼낸다."""
    picked = pick_items(ALL, "pythonw.exe")
    assert [i.key for i in picked] == ["b1"]


def test_the_claude_desktop_app_does_not_collide():
    """데스크톱 앱 항목은 툴팁이 비어 있어 접두사에 걸리지 않는다 (실측)."""
    assert CLAUDE_DESKTOP not in pick_items(ALL, "Claude.exe")


def test_a_guid_prefixed_path_is_matched_by_its_leaf_name():
    """GUID를 SHGetKnownFolderPath로 풀지 않는다. 아이콘 고정은 실패해도 조용히
    넘어가는 기능이라 그만한 정확도가 필요하지 않고, 파일 이름 비교만으로
    GUID 접두사가 자연히 흡수된다."""
    ours = NotifyItem(
        key="d1",
        tooltip="Claude 사용량\n불러오는 중",
        exe_path=r"{6D809377-6AF0-444B-8957-A3773F02200E}\Claude\ClaudeUsageOverlay.exe",
        promoted=False,
    )
    assert pick_items([ours], "ClaudeUsageOverlay.exe") == [ours]


def test_every_matching_item_is_returned():
    """같은 실행 파일에 항목이 여럿 생긴다 (실측: vgtray 4개, explorer 5개).
    소스로 돌리다 exe로 옮기면 우리 것도 여러 개가 된다."""
    twins = [
        NotifyItem("e1", "Claude 사용량\n불러오는 중", r"C:\x\app.exe", False),
        NotifyItem("e2", "Claude 사용량\n5시간 창  10%", r"C:\x\app.exe", True),
    ]
    assert [i.key for i in pick_items(twins, "app.exe")] == ["e1", "e2"]


def test_the_path_only_narrows_it_never_excludes_everything():
    """경로가 하나도 안 맞으면 툴팁으로 걸린 것을 **전부** 돌려준다.
    exe를 C:\\Program Files\\로 옮기면 sys.executable과의 비교가 어긋나는데,
    그때 빈 목록을 돌려주면 기능이 아무 표시 없이 죽는다 (스펙 2.8절)."""
    picked = pick_items([OURS_PYTHONW, OURS_EXE], "전혀다른이름.exe")
    assert [i.key for i in picked] == ["b1", "b2"]


def test_nothing_ours_means_an_empty_list():
    assert pick_items([POWERTOYS, EXPLORER, OTHER_PYTHONW], "pythonw.exe") == []


def test_promote_when_ready_waits_for_the_item_to_appear(monkeypatch):
    """항목은 아이콘이 한 번 뜬 뒤에야 탐색기가 만든다. 기동 직후에는 없다."""
    calls = []
    tries = []

    def fake_promote(value=True, name=None):
        tries.append(value)
        return len(tries) >= 3      # 세 번째에 나타난다

    monkeypatch.setattr(tp, "promote", fake_promote)
    assert tp.promote_when_ready(attempts=5, delay=0.5, sleep=calls.append) is True
    assert len(tries) == 3
    assert calls == [0.5, 0.5], "실패한 두 번 뒤에만 기다린다"


def test_promote_when_ready_gives_up_quietly(monkeypatch):
    """끝내 못 찾으면 조용히 포기한다. 예외를 던지면 기동이 멈춘다."""
    monkeypatch.setattr(tp, "promote", lambda value=True, name=None: False)
    assert tp.promote_when_ready(attempts=3, delay=0, sleep=lambda _s: None) is False


def test_exe_name_is_just_the_leaf():
    assert "\\" not in tp.exe_name() and "/" not in tp.exe_name()
    assert tp.exe_name().lower().endswith(".exe")
```

- [ ] **Step 2: 테스트를 돌려 실패 확인**

```bash
python -m pytest tests/test_tray_promote.py -v
```

예상: `ModuleNotFoundError: No module named 'claude_usage_overlay.tray_promote'`.

- [ ] **Step 3: `tray_promote.py` 작성**

```python
"""작업 표시줄에 트레이 아이콘을 고정한다. Windows 11 전용.

**즉시 반영되지 않는다.** Windows 11은 아이콘 표시 여부를
HKCU\\Control Panel\\NotifyIconSettings\\<해시>의 IsPromoted DWORD에 담는데,
탐색기가 이 값을 시작할 때 읽고 그 뒤로는 자기 캐시를 쓴다. 실측으로 셋 다
실패했다 — 값만 쓰기 · 값 쓴 뒤 아이콘 재등록 · WM_SETTINGCHANGE 7종 브로드캐스트.

**탐색기를 재시작하지 않는다.** 사용자의 열린 창을 전부 건드리는 짓이다.
따라서 이 기능은 **"다음 로그온부터 보이게 만드는" 기능**이고, 지금 당장 보려면
∧를 눌러 아이콘을 끌어다 놓아야 한다. 드래그가 먹히는 이유는 탐색기 자신이 그
변경을 하기 때문이다 — 레지스트리가 원인이 아니라 결과다.

**Windows 10은 하지 않는다.** Win10은 IconStreams 이진 blob에 담고 형식이
문서화돼 있지 않아 OS 버전마다 바뀔 수 있다. 전역 스위치(EnableAutoTray=0)는
있지만 모든 앱에 적용되므로 우리가 조용히 켤 값이 아니다. Win10에는 아이콘별
설정 화면이 따로 있으니 안내는 그쪽을 가리킨다 (first_run.py).

HKCU만 건드린다. 관리자 권한이 필요 없고, 우리가 만들지 않은 항목에는 쓰지 않는다.
"""

import sys
import time
import winreg
from dataclasses import dataclass
from pathlib import Path

NOTIFY_KEY = r"Control Panel\NotifyIconSettings"

# InitialTooltip에는 툴팁이 줄바꿈까지 그대로 들어 있다. 실측으로 우리 항목은
# "Claude 사용량\n불러오는 중"이었고, 51개 중 이것으로 시작하는 것은 우리뿐이다 —
# Claude 데스크톱 앱 항목은 툴팁이 비어 있어 겹치지 않는다.
#
# tray._tooltip()이 만드는 첫 줄과 같아야 한다. 그쪽을 고치면 여기도 고친다.
TOOLTIP_PREFIX = "Claude 사용량"


@dataclass(frozen=True)
class NotifyItem:
    key: str        # NotifyIconSettings 하위 키 이름 (해시)
    tooltip: str    # InitialTooltip
    exe_path: str   # ExecutablePath. **절대 경로가 아닐 수 있다** (머리말)
    promoted: bool


# --- 판정 (순수 함수) ----------------------------------------------------


def _leaf(path: str) -> str:
    return path.replace("/", "\\").rsplit("\\", 1)[-1].lower()


def pick_items(items: list[NotifyItem], exe_name: str) -> list[NotifyItem]:
    """항목 목록에서 우리 것.

    **툴팁을 주 조건으로 두고 경로는 후보를 가리는 데만 쓴다.** ExecutablePath는
    시스템 폴더 아래에서 KNOWNFOLDERID GUID 접두사로 저장되고(실측), 설치
    프로그램이 없으므로 사용자가 exe를 C:\\Program Files\\에 두는 순간
    sys.executable과의 문자열 비교가 어긋난다. 필수 조건으로 쓰면 그 순간 기능이
    아무 표시 없이 죽는다.

    경로 비교는 **파일 이름만** 본다. GUID를 SHGetKnownFolderPath로 풀 수는 있고
    실측으로 셋 다 풀렸지만, 아이콘 고정은 실패해도 조용히 넘어가는 기능이라
    그만한 정확도가 필요하지 않다. 이름 비교만으로 GUID 접두사가 자연히 흡수된다.

    **맞는 항목이 여럿이면 전부 돌려준다.** 같은 실행 파일에 항목이 여러 개
    생기는 것을 실측했다(vgtray 4개, explorer 5개). 소스로 돌리다 exe로 옮기면
    우리 것도 여러 개가 된다.
    """
    ours = [i for i in items if i.tooltip.startswith(TOOLTIP_PREFIX)]
    narrowed = [i for i in ours if _leaf(i.exe_path) == exe_name.lower()]
    return narrowed or ours


def exe_name() -> str:
    """지금 프로세스의 실행 파일 이름. 소스로 돌리면 pythonw.exe다."""
    return Path(sys.executable).name


# --- 레지스트리 (얇은 껍데기) --------------------------------------------


def is_supported() -> bool:
    """키가 있는 환경인지. Windows 10 이하에는 없다."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, NOTIFY_KEY):
            return True
    except OSError:
        return False


def _read_one(parent, name: str) -> NotifyItem | None:
    def value(key, field, default):
        try:
            got, _type = winreg.QueryValueEx(key, field)
            return got
        except OSError:
            return default

    try:
        with winreg.OpenKey(parent, name) as sub:
            return NotifyItem(
                key=name,
                tooltip=str(value(sub, "InitialTooltip", "")),
                exe_path=str(value(sub, "ExecutablePath", "")),
                promoted=bool(value(sub, "IsPromoted", 0)),
            )
    except OSError:
        return None


def read_items() -> list[NotifyItem]:
    """하위 키를 전부 읽는다. 못 읽으면 빈 목록 — 예외를 던지지 않는다."""
    items: list[NotifyItem] = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, NOTIFY_KEY) as parent:
            index = 0
            while True:
                try:
                    name = winreg.EnumKey(parent, index)
                except OSError:
                    break
                index += 1
                item = _read_one(parent, name)
                if item is not None:
                    items.append(item)
    except OSError:
        return []
    return items


def write_promoted(keys: list[str], value: bool) -> bool:
    """IsPromoted를 쓴다. 하나라도 썼으면 True."""
    if not keys:
        return False
    written = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, NOTIFY_KEY) as parent:
            for name in keys:
                try:
                    with winreg.OpenKey(parent, name, 0, winreg.KEY_SET_VALUE) as sub:
                        winreg.SetValueEx(
                            sub, "IsPromoted", 0, winreg.REG_DWORD, 1 if value else 0
                        )
                    written += 1
                except OSError:
                    continue
    except OSError:
        return False
    return written > 0


def is_promoted(name: str | None = None) -> bool:
    """우리 항목이 모두 고정돼 있는지. 항목이 없으면 False.

    쓰고 나서 이 함수로 다시 읽어 체크박스를 그린다. 안 그러면 화면이 거짓말을 한다.
    """
    ours = pick_items(read_items(), name or exe_name())
    return bool(ours) and all(i.promoted for i in ours)


def promote(value: bool = True, name: str | None = None) -> bool:
    """찾아서 쓴다. 못 찾으면 조용히 False."""
    ours = pick_items(read_items(), name or exe_name())
    return write_promoted([i.key for i in ours], value)


def promote_when_ready(
    attempts: int = 10,
    delay: float = 3.0,
    sleep=time.sleep,
    name: str | None = None,
) -> bool:
    """항목이 생길 때까지 기다렸다 쓴다. 별도 스레드에서 부른다.

    **항목은 아이콘이 한 번 뜬 뒤에야 탐색기가 만든다.** 기동 직후에는 없으므로
    한 번 보고 포기하면 첫 실행 자동 시도가 늘 실패한다. 기본값이면 최대 30초쯤
    기다리고, 끝내 못 찾으면 조용히 포기한다 — 예외를 던지면 기동이 멈춘다.
    """
    for remaining in range(attempts, 0, -1):
        if promote(True, name):
            return True
        if remaining > 1:
            sleep(delay)
    return False
```

- [ ] **Step 4: 테스트를 돌려 통과 확인**

```bash
python -m pytest tests/test_tray_promote.py -v
```

예상: 전부 PASS. `test_exe_name_is_just_the_leaf`는 이 PC의
`sys.executable`이 `python.exe`이므로 통과한다.

- [ ] **Step 5: 실제 레지스트리에서 우리 항목이 잡히는지 확인**

```bash
python -c "from claude_usage_overlay import tray_promote as t; items=t.read_items(); print(len(items), '개'); print([(i.key, i.tooltip.splitlines()[:1], i.promoted) for i in t.pick_items(items, 'pythonw.exe')])"
```

예상: 항목 수가 40~60개쯤 나오고, 우리 것이 0개 또는 그 이상 나온다. **0개는
정상이다** — `pythonw.exe`로 한 번도 띄운 적이 없으면 항목이 없다. 이때는
`python -m claude_usage_overlay`를 한 번 띄웠다 끄고 `python.exe`로 다시 확인한다.
여기서 `read_items()`가 예외를 던지면 껍데기가 잘못됐다.

- [ ] **Step 6: 커밋**

```bash
git add claude_usage_overlay/tray_promote.py tests/test_tray_promote.py
git commit -m "feat: NotifyIconSettings 항목을 툴팁으로 찾아 IsPromoted를 쓰는 tray_promote 추가"
```

---

## Task 8: widget_paint — 위젯 셋이 공유하는 PIL 조각

**파일:**
- 생성: `claude_usage_overlay/widget_paint.py`
- 테스트: `tests/test_widget_paint.py`

**인터페이스:**
- 사용: `ring_render._rgb(color: str) -> tuple[int, int, int]` (기존. `build.py:32`도 같은 함수를 import해 쓰고 있으므로 밑줄 이름을 가져다 쓰는 선례가 있다)
- 제공:
  - `widget_paint.rounded_box(w: int, h: int, radius: int, fill: str | None = None, outline: str | None = None, width: int = 1, bg: str = theme.BG) -> Image.Image`
  - `widget_paint.circle(diameter: int, fill: str, bg: str = theme.BG) -> Image.Image`
  - `widget_paint.SUPERSAMPLE: int = 4`

- [ ] **Step 1: 실패하는 테스트 작성 — `tests/test_widget_paint.py`**

```python
"""위젯 조각. 창 없이 픽셀만 잰다.

캔버스 create_rectangle·create_oval에는 안티앨리어싱이 없어(ring_render 머리말)
둥근 모서리와 작은 원이 픽셀 계단으로 드러난다. 그래서 크게 그려 축소한다 —
이 테스트는 그 축소가 실제로 중간톤을 만들어내는지 잰다.
"""

from claude_usage_overlay import theme
from claude_usage_overlay.ring_render import _rgb
from claude_usage_overlay.widget_paint import circle, rounded_box


def test_the_box_is_exactly_the_requested_size():
    """치수가 어긋나면 배율 있는 PC에서 위젯이 서로 안 맞는다."""
    assert rounded_box(16, 16, 4, fill=theme.GREEN).size == (16, 16)
    assert rounded_box(120, 6, 3, fill=theme.YELLOW).size == (120, 6)


def test_the_middle_of_a_filled_box_is_the_fill_color():
    img = rounded_box(16, 16, 4, fill=theme.GREEN)
    assert img.getpixel((8, 8))[:3] == _rgb(theme.GREEN)


def test_the_corner_is_a_blend_not_a_staircase():
    """축소가 곧 안티앨리어싱이다. 모서리에 배경도 채움도 아닌 색이 있어야 한다."""
    img = rounded_box(16, 16, 5, fill=theme.GREEN)
    corner = [img.getpixel((x, y))[:3] for x in range(6) for y in range(6)]
    blends = [c for c in corner if c != _rgb(theme.GREEN) and c != _rgb(theme.BG)]
    assert blends, "중간톤이 하나도 없다 — 축소가 안 걸렸다"


def test_an_outline_only_box_keeps_the_background_inside():
    """꺼진 체크박스는 테두리만 그린다. 안이 칠해지면 켜진 것과 구분이 안 된다."""
    img = rounded_box(16, 16, 4, outline=theme.TEXT_DIM, width=1)
    assert img.getpixel((8, 8))[:3] == _rgb(theme.BG)
    edge = [img.getpixel((x, 8))[:3] for x in range(3)]
    assert any(c != _rgb(theme.BG) for c in edge), "테두리가 안 보인다"


def test_the_circle_is_round_not_square():
    """손잡이가 사각형이면 슬라이더가 아니라 스크롤바로 보인다."""
    img = circle(14, theme.YELLOW)
    assert img.getpixel((7, 7))[:3] == _rgb(theme.YELLOW)
    assert img.getpixel((0, 0))[:3] == _rgb(theme.BG)


def test_the_background_is_opaque():
    """어두운 창 위에 얹으므로 알파 합성을 Tk에 맡기지 않는다.
    ring_render가 RGBA 대신 불투명 bg를 쓰는 것과 같은 이유다."""
    assert rounded_box(16, 16, 4, fill=theme.GREEN).mode == "RGB"
    assert circle(14, theme.YELLOW).mode == "RGB"


def test_a_custom_background_is_honored():
    """드롭다운 목록은 창 배경이 아니라 자기 패널 위에 그린다."""
    img = rounded_box(16, 16, 4, fill=theme.GREEN, bg=theme.RING_TRACK)
    assert img.getpixel((0, 0))[:3] == _rgb(theme.RING_TRACK)
```

- [ ] **Step 2: 테스트를 돌려 실패 확인**

```bash
python -m pytest tests/test_widget_paint.py -v
```

예상: `ModuleNotFoundError: No module named 'claude_usage_overlay.widget_paint'`.

- [ ] **Step 3: `widget_paint.py` 작성**

```python
"""체크박스·슬라이더·드롭다운이 함께 쓰는 PIL 그림 조각.

**스펙 10장의 모듈 표에 없는 파일이다.** 세 위젯이 같은 둥근 사각형을 그리므로
세 번 베끼는 대신 여기 모았다.

캔버스 create_rectangle·create_oval에는 안티앨리어싱이 없다(ring_render 머리말).
둥근 모서리와 작은 원에서 픽셀 계단이 그대로 드러나므로, 링과 트레이 아이콘처럼
SUPERSAMPLE배 크게 그린 뒤 축소한다. 축소가 곧 안티앨리어싱이다.

배경은 투명(RGBA)이 아니라 불투명 bg로 채운다. 설정창 배경이 어차피 한 색이고,
알파 합성을 Tk에 맡기지 않는 편이 결과가 확실하다 — ring_render와 같은 판단이다.
"""

from PIL import Image, ImageDraw

from . import theme
from .ring_render import _rgb

SUPERSAMPLE = 4   # ring_render와 같은 값. 8배로 올려도 눈에 띄는 차이가 없다


def rounded_box(
    w: int,
    h: int,
    radius: int,
    fill: str | None = None,
    outline: str | None = None,
    width: int = 1,
    bg: str = theme.BG,
) -> Image.Image:
    """모서리를 둥글게 깎은 사각형. fill 없이 outline만 주면 테두리만 그린다."""
    s = SUPERSAMPLE
    big = Image.new("RGB", (max(1, w) * s, max(1, h) * s), _rgb(bg))
    stroke = max(1, width * s)
    # 선은 경계선 안쪽으로 그려지므로 두께의 절반만큼 들여야 잘리지 않는다.
    inset = stroke // 2
    ImageDraw.Draw(big).rounded_rectangle(
        [inset, inset, big.width - 1 - inset, big.height - 1 - inset],
        radius=radius * s,
        fill=_rgb(fill) if fill else None,
        outline=_rgb(outline) if outline else None,
        width=stroke,
    )
    # BOX(단순 평균)를 쓴다. LANCZOS는 경계 바깥에 밝은 테두리를 남기는데
    # 어두운 배경 위에서는 그 오버슈트가 눈에 띈다.
    return big.resize((max(1, w), max(1, h)), Image.BOX)


def circle(diameter: int, fill: str, bg: str = theme.BG) -> Image.Image:
    """슬라이더 손잡이. 사각형으로 보이면 스크롤바와 구분이 안 된다."""
    s = SUPERSAMPLE
    d = max(1, diameter)
    big = Image.new("RGB", (d * s, d * s), _rgb(bg))
    ImageDraw.Draw(big).ellipse([0, 0, d * s - 1, d * s - 1], fill=_rgb(fill))
    return big.resize((d, d), Image.BOX)
```

- [ ] **Step 4: 테스트를 돌려 통과 확인**

```bash
python -m pytest tests/test_widget_paint.py -v
```

- [ ] **Step 5: 커밋**

```bash
git add claude_usage_overlay/widget_paint.py tests/test_widget_paint.py
git commit -m "feat: 위젯 셋이 공유하는 PIL 조각(둥근 사각형·원) 추가"
```

---

## Task 9: checkbox — 캔버스 체크박스

ttk 기본 위젯은 윈도우 기본 테마에서 색이 먹지 않는다. 어두운 설정창에 얹으면
밝은 사각형이 남는다.

**파일:**
- 생성: `claude_usage_overlay/checkbox.py`
- 테스트: `tests/test_checkbox.py`

**인터페이스:**
- 사용: `widget_paint.rounded_box` (Task 8), `theme.GREEN` · `TEXT_LIGHT` · `TEXT_DIM` · `BG` · `TEXT_DARK` · `GREY`
- 제공:
  - `checkbox.BOX: int = 16` · `RADIUS: int = 4` · `LABEL_GAP: int = 8` · `CHECK_WIDTH: int = 2`
  - `checkbox.check_points(x0: float, y0: float, size: float) -> list[tuple[float, float]]`
  - `checkbox.Checkbox(parent, text: str, checked: bool, on_toggle: Callable[[bool], None], scale: float, font: tuple, indent: int = 0)` — 메서드 `widget() -> tk.Canvas` · `set_checked(bool)` · `set_enabled(bool)` · `checked() -> bool`

- [ ] **Step 1: 실패하는 테스트 작성 — `tests/test_checkbox.py`**

```python
"""체크 표시의 기하. 창 없이 좌표만 잰다."""

from claude_usage_overlay.checkbox import check_points


def test_the_check_is_three_points_not_a_glyph():
    """글리프(`✓`)를 쓰면 글꼴마다 모양이 달라지고 획이 가늘다.
    끝이 둥근 두꺼운 선 둘로 긋는다 — 그러려면 꺾이는 점이 하나 필요하다."""
    assert len(check_points(0, 0, 16)) == 3


def test_the_check_stays_inside_the_box():
    """상자를 넘으면 체크가 잘리거나 옆 글자를 덮는다."""
    for size in (12, 16, 20, 24):
        for x, y in check_points(0, 0, size):
            assert 0 <= x <= size, (size, x)
            assert 0 <= y <= size, (size, y)


def test_the_left_stroke_is_shorter_than_the_right():
    """보통 체크 모양이다. 두 획이 같은 길이면 V자로 보인다."""
    (ax, ay), (bx, by), (cx, cy) = check_points(0, 0, 16)
    left = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
    right = ((cx - bx) ** 2 + (cy - by) ** 2) ** 0.5
    assert left < right


def test_the_middle_point_is_the_lowest():
    """꺾이는 점이 가장 아래여야 체크로 보인다."""
    points = check_points(0, 0, 16)
    assert points[1][1] == max(y for _x, y in points)


def test_the_points_move_with_the_box():
    """상자 위치를 더하기만 한다. 배율마다 상자가 다른 자리에 놓인다."""
    base = check_points(0, 0, 16)
    moved = check_points(10, 20, 16)
    assert [(x + 10, y + 20) for x, y in base] == moved


def test_the_shape_scales_with_the_box():
    """비율로 두는 이유는 배율마다 상자 크기가 달라지기 때문이다."""
    small = check_points(0, 0, 16)
    big = check_points(0, 0, 32)
    assert [(x * 2, y * 2) for x, y in small] == big
```

- [ ] **Step 2: 테스트를 돌려 실패 확인**

```bash
python -m pytest tests/test_checkbox.py -v
```

예상: `ModuleNotFoundError`.

- [ ] **Step 3: `checkbox.py` 작성**

```python
"""캔버스 체크박스.

ttk.Checkbutton은 윈도우 기본 테마에서 배경·전경색이 먹지 않는다. 어두운
설정창에 얹으면 밝은 사각형이 남는다. 링과 트레이 아이콘을 이미 PIL로 그리고
있으므로 이 코드베이스에 낯선 방식은 아니다.

**체크 표시는 글꼴 글리프(`✓`)가 아니라 끝이 둥근 두꺼운 선 둘로 긋는다.**
글리프를 쓰면 글꼴마다 모양이 달라지고 획이 가늘다. capstyle="round"·
joinstyle="round"로 끝과 꺾임을 둥글게 만든다.

상자 자체는 PIL로 그린다 — 캔버스에는 둥근 사각형이 없고, create_polygon의
smooth는 스플라인이라 반경을 못 정한다 (widget_paint 머리말).
"""

import tkinter as tk
from typing import Callable

from . import theme
from .widget_paint import rounded_box
from PIL import ImageTk

BOX = 16          # 상자 한 변 (기준 픽셀)
RADIUS = 4
LABEL_GAP = 8     # 상자와 글자 사이
CHECK_WIDTH = 2
PAD_Y = 5         # 위아래 여백. 클릭 판정 높이가 이만큼 넉넉해진다


def check_points(x0: float, y0: float, size: float) -> list[tuple[float, float]]:
    """체크 표시의 꺾은선. (x0, y0)은 상자 왼쪽 위, size는 한 변.

    비율로 두는 이유는 배율마다 상자 크기가 달라지기 때문이다. 세 점은 눈으로
    고른 값이고, 왼쪽 획이 짧고 오른쪽이 긴 보통 체크 모양이다.
    """
    return [
        (x0 + size * 0.26, y0 + size * 0.52),
        (x0 + size * 0.44, y0 + size * 0.72),
        (x0 + size * 0.76, y0 + size * 0.30),
    ]


class Checkbox:
    """한 줄짜리 캔버스. 상자와 글자를 함께 담고 줄 전체가 클릭 판정이다.

    글자만 클릭 가능하게 두면 16px 상자를 정확히 노려야 하고, 줄 전체를 판정으로
    두면 실수로 눌리는 일이 늘지만 설정창의 값들은 다시 고르면 그만이다.
    """

    def __init__(
        self,
        parent: tk.Misc,
        text: str,
        checked: bool,
        on_toggle: Callable[[bool], None],
        scale: float,
        font: tuple,
        indent: int = 0,
        width: int | None = None,
    ) -> None:
        self._on_toggle = on_toggle
        self._checked = checked
        self._enabled = True
        self._text = text
        self._font = font

        self._box = round(BOX * scale)
        self._radius = max(2, round(RADIUS * scale))
        self._gap = round(LABEL_GAP * scale)
        self._check_width = max(2, round(CHECK_WIDTH * scale))
        self._indent = round(indent * scale)
        self._pad_y = round(PAD_Y * scale)

        height = self._box + self._pad_y * 2
        self._canvas = tk.Canvas(
            parent,
            width=width or 1,
            height=height,
            bg=theme.BG,
            highlightthickness=0,
            cursor="hand2",
        )
        self._canvas.bind("<Button-1>", self._click)

        # PhotoImage는 참조가 끊기면 화면에서 사라진다. 두 상태를 미리 만들어 든다.
        self._images = {
            (True, True): self._image(fill=theme.GREEN),
            (False, True): self._image(outline=theme.TEXT_DIM),
            (True, False): self._image(fill=theme.GREY),
            (False, False): self._image(outline=theme.GREY),
        }
        self._draw()

    # --- 공개 인터페이스 -------------------------------------------------

    def widget(self) -> tk.Canvas:
        return self._canvas

    def checked(self) -> bool:
        return self._checked

    def set_checked(self, checked: bool) -> None:
        """밖에서 값이 바뀌었을 때 화면만 맞춘다. on_toggle을 부르지 않는다 —
        부르면 설정창 동기화(스펙 4.4절)가 무한히 되울린다."""
        if checked == self._checked:
            return
        self._checked = checked
        self._draw()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._canvas.configure(cursor="hand2" if enabled else "")
        self._draw()

    # --- 내부 ------------------------------------------------------------

    def _image(self, fill=None, outline=None) -> ImageTk.PhotoImage:
        return ImageTk.PhotoImage(
            rounded_box(self._box, self._box, self._radius, fill=fill, outline=outline)
        )

    def _click(self, _event) -> None:
        if not self._enabled:
            return
        self._checked = not self._checked
        self._draw()
        self._on_toggle(self._checked)

    def _draw(self) -> None:
        c = self._canvas
        c.delete("all")
        x = self._indent
        c.create_image(
            x, self._pad_y, image=self._images[(self._checked, self._enabled)], anchor="nw"
        )
        if self._checked:
            # 체크 색은 채움 위에 얹히므로 어두워야 한다. 흰 체크를 GREEN 위에
            # 얹으면 대비가 3:1 아래로 떨어진다 (theme.py 주석과 같은 이유).
            c.create_line(
                *[p for point in check_points(x, self._pad_y, self._box) for p in point],
                fill=theme.TEXT_DARK if self._enabled else theme.BG,
                width=self._check_width,
                capstyle="round",
                joinstyle="round",
            )
        c.create_text(
            x + self._box + self._gap,
            self._pad_y + self._box / 2,
            text=self._text,
            anchor="w",
            fill=theme.TEXT_LIGHT if self._enabled else theme.TEXT_DIM,
            font=self._font,
        )
```

- [ ] **Step 4: 테스트를 돌려 통과 확인**

```bash
python -m pytest tests/test_checkbox.py -v
```

- [ ] **Step 5: 커밋**

```bash
git add claude_usage_overlay/checkbox.py tests/test_checkbox.py
git commit -m "feat: 캔버스 체크박스 추가 (체크는 글리프가 아니라 둥근 선 둘)"
```

---

## Task 10: slider — 캔버스 슬라이더

값↔픽셀 환산·클램프·5단위 스냅은 순수 함수로 빼서 창 없이 테스트한다.

**파일:**
- 생성: `claude_usage_overlay/slider.py`
- 테스트: `tests/test_slider.py`

**인터페이스:**
- 사용: `widget_paint.rounded_box` · `widget_paint.circle` (Task 8), `config.PCT_STEP` · `PCT_MIN` · `PCT_MAX` (Task 3)
- 제공:
  - `slider.TRACK_HEIGHT: int = 6` · `HANDLE: int = 14` · `VALUE_GAP: int = 10` · `VALUE_WIDTH: int = 34`
  - `slider.clamp(value: float, lo: int, hi: int) -> int`
  - `slider.snap(value: float, step: int) -> int`
  - `slider.value_to_x(value: int, lo: int, hi: int, x0: int, x1: int) -> int`
  - `slider.x_to_value(x: int, lo: int, hi: int, x0: int, x1: int, step: int) -> int`
  - `slider.Slider(parent, width, lo, hi, step, value, color, on_change, scale, font)` — 메서드 `widget() -> tk.Canvas` · `value() -> int` · `set_bounds(lo, hi)` · `set_value(v)`

- [ ] **Step 1: 실패하는 테스트 작성 — `tests/test_slider.py`**

```python
"""슬라이더 기하. 창 없이 산수만 잰다.

손잡이 반지름만큼 좌우를 들여야 손잡이가 트랙 밖으로 안 나간다. 그 들여쓰기를
빼먹으면 최솟값·최댓값에서 손잡이의 절반이 잘리는데, 화면에서는 "끝까지 안 간다"로
보여서 원인을 찾기 어렵다.
"""

import pytest

from claude_usage_overlay.config import PCT_MAX, PCT_MIN, PCT_STEP
from claude_usage_overlay.slider import clamp, snap, value_to_x, x_to_value

X0, X1 = 20, 200   # 트랙의 왼쪽·오른쪽 끝 (손잡이 중심이 갈 수 있는 범위)


def test_clamp_keeps_a_value_inside_the_range():
    assert clamp(30, 50, 100) == 50
    assert clamp(120, 50, 100) == 100
    assert clamp(70, 50, 100) == 70


def test_snap_rounds_to_the_nearest_step():
    """세밀함보다 손으로 맞추기 쉬운 쪽을 골랐다 (스펙 4.1절)."""
    assert snap(71, 5) == 70
    assert snap(73, 5) == 75
    assert snap(72.5, 5) == 75, "경계는 위로 — round()의 은행가 반올림을 쓰면 안 된다"


def test_the_ends_land_on_the_track_ends():
    assert value_to_x(PCT_MIN, PCT_MIN, PCT_MAX, X0, X1) == X0
    assert value_to_x(PCT_MAX, PCT_MIN, PCT_MAX, X0, X1) == X1


def test_the_middle_lands_in_the_middle():
    assert value_to_x(75, 50, 100, X0, X1) == (X0 + X1) // 2


@pytest.mark.parametrize("value", range(PCT_MIN, PCT_MAX + 1, PCT_STEP))
def test_value_to_pixel_and_back_is_a_round_trip(value):
    """왕복이 어긋나면 손잡이를 안 건드렸는데 값이 한 칸 움직인다."""
    x = value_to_x(value, PCT_MIN, PCT_MAX, X0, X1)
    assert x_to_value(x, PCT_MIN, PCT_MAX, X0, X1, PCT_STEP) == value


def test_dragging_past_the_ends_is_clamped():
    assert x_to_value(X0 - 500, PCT_MIN, PCT_MAX, X0, X1, PCT_STEP) == PCT_MIN
    assert x_to_value(X1 + 500, PCT_MIN, PCT_MAX, X0, X1, PCT_STEP) == PCT_MAX


def test_the_result_is_always_on_a_step():
    """5단위가 아닌 값이 나오면 설정창이 파일에 73 같은 값을 쓰고, 다시 열면
    손잡이가 눈금 사이에 선다."""
    for x in range(X0 - 20, X1 + 20):
        got = x_to_value(x, PCT_MIN, PCT_MAX, X0, X1, PCT_STEP)
        assert got % PCT_STEP == 0, (x, got)


def test_a_narrow_track_does_not_divide_by_zero():
    """창을 아주 좁게 만든 배율에서 x0 == x1이 될 수 있다."""
    assert x_to_value(50, 50, 100, 100, 100, 5) == 50
    assert value_to_x(70, 50, 100, 100, 100) == 100


def test_a_single_point_range_does_not_divide_by_zero():
    """노란 슬라이더의 상한이 빨간에 맞춰 좁아지다 한 점이 될 수 있다."""
    assert value_to_x(50, 50, 50, X0, X1) == X0
    assert x_to_value(150, 50, 50, X0, X1, 5) == 50
```

- [ ] **Step 2: 테스트를 돌려 실패 확인**

```bash
python -m pytest tests/test_slider.py -v
```

- [ ] **Step 3: `slider.py` 작성**

```python
"""캔버스 슬라이더.

ttk.Scale은 윈도우 기본 테마에서 색이 먹지 않고, 무엇보다 **채운 부분을
그 기준의 색으로 칠할 수 없다.** 노란 기준은 노랑, 빨간 기준은 빨강으로
칠하면 무엇을 정하는 값인지 글자를 안 읽어도 보인다 (스펙 4.2절).

값↔픽셀 환산은 순수 함수로 빼서 창 없이 테스트한다. 여기가 조용히 틀리면
화면에서는 "손잡이가 끝까지 안 간다"로 보여서 원인을 찾기 어렵다.
"""

import tkinter as tk
from typing import Callable

from PIL import ImageTk

from . import theme
from .widget_paint import circle, rounded_box

TRACK_HEIGHT = 6
HANDLE = 14
VALUE_GAP = 10    # 트랙과 값 글자 사이
VALUE_WIDTH = 34  # `100%`가 들어가는 폭


# --- 판정 (순수 함수) ----------------------------------------------------


def clamp(value: float, lo: int, hi: int) -> int:
    return int(max(lo, min(hi, value)))


def snap(value: float, step: int) -> int:
    """가장 가까운 눈금으로. **경계는 위로 붙인다.**

    round()를 쓰면 안 된다. 은행가 반올림이라 72.5가 70으로 가고 77.5는 80으로
    가서, 손잡이를 같은 만큼 끌었는데 결과가 갈린다.
    """
    if step <= 0:
        return int(value)
    return int((value + step / 2) // step) * step


def value_to_x(value: int, lo: int, hi: int, x0: int, x1: int) -> int:
    """값 → 손잡이 중심의 x. x0·x1은 **손잡이 중심**이 갈 수 있는 범위다.

    트랙의 픽셀 범위가 아니라 중심 범위를 받는 이유는, 부르는 쪽이 손잡이
    반지름만큼 이미 들여놨기 때문이다. 안 들이면 최솟값·최댓값에서 손잡이의
    절반이 잘린다.
    """
    if hi <= lo:
        return x0
    ratio = (clamp(value, lo, hi) - lo) / (hi - lo)
    return round(x0 + ratio * (x1 - x0))


def x_to_value(x: int, lo: int, hi: int, x0: int, x1: int, step: int) -> int:
    """손잡이 중심의 x → 값. 범위 밖은 끝값으로 붙이고 눈금으로 스냅한다."""
    if hi <= lo or x1 <= x0:
        return lo
    ratio = (x - x0) / (x1 - x0)
    return clamp(snap(lo + ratio * (hi - lo), step), lo, hi)


# --- 위젯 ----------------------------------------------------------------


class Slider:
    def __init__(
        self,
        parent: tk.Misc,
        width: int,
        lo: int,
        hi: int,
        step: int,
        value: int,
        color: str,
        on_change: Callable[[int], None],
        scale: float,
        font: tuple,
    ) -> None:
        self._lo, self._hi, self._step = lo, hi, step
        self._value = clamp(snap(value, step), lo, hi)
        self._color = color
        self._on_change = on_change
        self._font = font

        self._handle = max(8, round(HANDLE * scale))
        self._track_h = max(3, round(TRACK_HEIGHT * scale))
        self._value_w = round(VALUE_WIDTH * scale)
        self._gap = round(VALUE_GAP * scale)

        self._h = self._handle + 2
        # 손잡이 중심이 갈 수 있는 범위. 반지름만큼 좌우를 들인다.
        r = self._handle // 2
        self._x0 = r
        self._x1 = width - self._value_w - self._gap - r

        self._canvas = tk.Canvas(
            parent, width=width, height=self._h, bg=theme.BG,
            highlightthickness=0, cursor="hand2",
        )
        for event in ("<Button-1>", "<B1-Motion>"):
            self._canvas.bind(event, self._on_mouse)

        self._handle_photo = ImageTk.PhotoImage(circle(self._handle, theme.TEXT_LIGHT))
        self._track_photos: dict[int, ImageTk.PhotoImage] = {}
        self._draw()

    # --- 공개 인터페이스 -------------------------------------------------

    def widget(self) -> tk.Canvas:
        return self._canvas

    def value(self) -> int:
        return self._value

    def set_value(self, value: int) -> None:
        self._value = clamp(snap(value, self._step), self._lo, self._hi)
        self._draw()

    def set_bounds(self, lo: int, hi: int) -> None:
        """노란은 빨간보다 5%p 아래에서 멈추고 반대도 같다. **서로 밀어내지 않고
        그 자리에 선다** — 그러려면 상대가 움직일 때마다 내 한계가 바뀐다."""
        self._lo, self._hi = lo, hi
        self.set_value(self._value)

    # --- 내부 ------------------------------------------------------------

    def _on_mouse(self, event) -> None:
        value = x_to_value(event.x, self._lo, self._hi, self._x0, self._x1, self._step)
        if value == self._value:
            return
        self._value = value
        self._draw()
        self._on_change(value)

    def _track(self, filled_w: int) -> ImageTk.PhotoImage:
        """채운 부분과 빈 부분을 한 그림으로 만든다. 값마다 캐시한다 —
        드래그 중에 1초에 수십 번 불린다."""
        photo = self._track_photos.get(filled_w)
        if photo is None:
            width = self._x1 + self._handle // 2
            radius = self._track_h // 2
            base = rounded_box(width, self._track_h, radius, fill=theme.RING_TRACK)
            if filled_w > 0:
                fill = rounded_box(filled_w, self._track_h, radius, fill=self._color)
                base.paste(fill, (0, 0))
            photo = ImageTk.PhotoImage(base)
            self._track_photos[filled_w] = photo
        return photo

    def _draw(self) -> None:
        c = self._canvas
        c.delete("all")
        cx = value_to_x(self._value, self._lo, self._hi, self._x0, self._x1)
        mid = self._h // 2

        c.create_image(0, mid - self._track_h // 2, image=self._track(cx), anchor="nw")
        c.create_image(cx - self._handle // 2, mid - self._handle // 2,
                       image=self._handle_photo, anchor="nw")
        c.create_text(
            self._x1 + self._handle // 2 + self._gap, mid,
            text=f"{self._value}%", anchor="w",
            fill=theme.TEXT_LIGHT, font=self._font,
        )
```

- [ ] **Step 4: 테스트를 돌려 통과 확인**

```bash
python -m pytest tests/test_slider.py -v
```

- [ ] **Step 5: 커밋**

```bash
git add claude_usage_overlay/slider.py tests/test_slider.py
git commit -m "feat: 캔버스 슬라이더 추가 (채운 부분을 그 기준의 색으로 칠함)"
```

---

## Task 11: dropdown — 조회 주기 드롭다운

2 · 5 · 10 · 30분. 2분이 하한이고 그 아래는 호출 한도에 걸린다
(`config.MIN_POLL_SECONDS`). 목록에 없는 값이 파일에 있으면 가장 가까운 항목으로
붙는다.

**파일:**
- 생성: `claude_usage_overlay/dropdown.py`
- 테스트: `tests/test_dropdown.py`

**인터페이스:**
- 사용: `widget_paint.rounded_box` (Task 8), `config.MIN_POLL_SECONDS` (기존)
- 제공:
  - `dropdown.POLL_CHOICES: tuple[tuple[int, str], ...]` — `((120, "2분"), (300, "5분"), (600, "10분"), (1800, "30분"))`
  - `dropdown.nearest(value: int, choices=POLL_CHOICES) -> int`
  - `dropdown.label_for(value: int, choices=POLL_CHOICES) -> str`
  - `dropdown.BORDER: int = 1` · `PAD_X: int = 10` · `ROW_H: int = 26` · `RADIUS: int = 5`
  - `dropdown.Dropdown(parent, choices, value, on_change, scale, font, width)` — 메서드 `widget() -> tk.Canvas` · `value() -> int` · `close()`

- [ ] **Step 1: 실패하는 테스트 작성 — `tests/test_dropdown.py`**

```python
"""드롭다운 판정. 창 없이 산수만 잰다."""

from claude_usage_overlay.config import MIN_POLL_SECONDS
from claude_usage_overlay.dropdown import POLL_CHOICES, label_for, nearest


def test_the_floor_is_the_first_choice():
    """2분 아래는 호출 한도에 걸린다. 드롭다운에 그 아래 항목을 두면 안 된다."""
    assert POLL_CHOICES[0][0] == MIN_POLL_SECONDS


def test_the_choices_are_sorted():
    """정렬돼 있지 않으면 펼친 목록이 뒤죽박죽으로 보인다."""
    values = [v for v, _label in POLL_CHOICES]
    assert values == sorted(values)


def test_an_exact_value_stays_put():
    for value, _label in POLL_CHOICES:
        assert nearest(value) == value


def test_a_hand_edited_value_snaps_to_the_closest_choice():
    """파일에 손으로 240초를 적어둔 경우다. 5분(300)이 2분(120)보다 가깝다.
    드롭다운으로 바꾼 이상 피할 수 없고, 닫으면 그 값이 저장된다 (스펙 4.1절)."""
    assert nearest(240) == 300


def test_a_tie_goes_to_the_longer_period():
    """210초는 120과 300에서 같은 거리다. 긴 쪽으로 붙인다 — 짧은 쪽을 고르면
    측정되지 않은 호출 한도에 더 가까워진다 (config.MIN_POLL_SECONDS 주석)."""
    assert nearest(210) == 300


def test_values_outside_the_list_are_pulled_to_the_ends():
    assert nearest(1) == 120
    assert nearest(86400) == 1800


def test_label_follows_the_value():
    assert label_for(300) == "5분"
    assert label_for(240) == "5분", "표시도 붙은 항목을 따라간다"
```

- [ ] **Step 2: 테스트를 돌려 실패 확인**

```bash
python -m pytest tests/test_dropdown.py -v
```

- [ ] **Step 3: `dropdown.py` 작성**

```python
"""캔버스 드롭다운.

ttk.Combobox는 윈도우 기본 테마에서 색이 먹지 않고, 펼친 목록은 아예 네이티브
창이라 손댈 수 없다.

**펼친 목록의 바깥 테두리를 단추의 바깥 테두리와 맞춘다.** 폭을 따로 적지 않고
좌우를 테두리 두께만큼 물려서, 항목 글자가 길어져도 어긋나지 않는다 (스펙 4.2절).

조회 주기를 드롭다운으로 만든 이유는 자유 입력에 하한이 필요하기 때문이다.
2분 아래는 호출 한도에 걸리고(config.MIN_POLL_SECONDS), 숫자를 직접 받으면
"왜 60이 안 되지"를 설명할 자리가 없다.
"""

import tkinter as tk
from typing import Callable

from PIL import ImageTk

from . import theme
from .config import MIN_POLL_SECONDS
from .widget_paint import rounded_box

# 첫 항목이 하한이다. config.MIN_POLL_SECONDS와 같아야 한다 — 어긋나면 목록에
# 고를 수 없는 값이 생기거나, 고르면 load_config가 조용히 올려버린다.
POLL_CHOICES = ((MIN_POLL_SECONDS, "2분"), (300, "5분"), (600, "10분"), (1800, "30분"))

BORDER = 1
PAD_X = 10
ROW_H = 26
RADIUS = 5
ARROW = 8    # ▾ 삼각형의 밑변


# --- 판정 (순수 함수) ----------------------------------------------------


def nearest(value: int, choices=POLL_CHOICES) -> int:
    """목록에서 가장 가까운 값.

    **같은 거리면 긴 쪽으로 붙인다.** 짧은 쪽을 고르면 측정되지 않은 호출 한도에
    더 가까워진다 — 하한 120초 자체가 측정값이 아니라는 것이
    config.MIN_POLL_SECONDS의 주석에 적혀 있다.
    """
    return min((v for v, _label in choices), key=lambda v: (abs(v - value), -v))


def label_for(value: int, choices=POLL_CHOICES) -> str:
    picked = nearest(value, choices)
    return next(label for v, label in choices if v == picked)


# --- 위젯 ----------------------------------------------------------------


class Dropdown:
    def __init__(
        self,
        parent: tk.Misc,
        choices,
        value: int,
        on_change: Callable[[int], None],
        scale: float,
        font: tuple,
        width: int,
    ) -> None:
        self._choices = tuple(choices)
        self._value = nearest(value, self._choices)
        self._on_change = on_change
        self._font = font
        self._open = False

        self._border = max(1, round(BORDER * scale))
        self._pad = round(PAD_X * scale)
        self._row = round(ROW_H * scale)
        self._radius = max(2, round(RADIUS * scale))
        self._arrow = round(ARROW * scale)
        self._w = width

        # 닫혔을 때는 단추 한 줄, 펼치면 그 아래로 항목이 늘어난다. 캔버스 높이를
        # 미리 최대로 잡아두면 그 아래 위젯이 밀려나므로 그때그때 바꾼다.
        self._canvas = tk.Canvas(
            parent, width=self._w, height=self._row, bg=theme.BG,
            highlightthickness=0, cursor="hand2",
        )
        self._canvas.bind("<Button-1>", self._click)

        self._button_photo = ImageTk.PhotoImage(
            rounded_box(self._w, self._row, self._radius,
                        outline=theme.TEXT_DIM, width=self._border)
        )
        self._panel_photo: ImageTk.PhotoImage | None = None
        self._draw()

    # --- 공개 인터페이스 -------------------------------------------------

    def widget(self) -> tk.Canvas:
        return self._canvas

    def value(self) -> int:
        return self._value

    def close(self) -> None:
        if self._open:
            self._open = False
            self._draw()

    # --- 내부 ------------------------------------------------------------

    def _panel_height(self) -> int:
        return self._row * len(self._choices)

    def _panel(self) -> ImageTk.PhotoImage:
        if self._panel_photo is None:
            self._panel_photo = ImageTk.PhotoImage(
                rounded_box(self._w, self._panel_height(), self._radius,
                            fill=theme.RING_TRACK, outline=theme.TEXT_DIM,
                            width=self._border)
            )
        return self._panel_photo

    def _click(self, event) -> None:
        if not self._open:
            self._open = True
            self._draw()
            return
        # 펼친 상태다. 단추 줄을 다시 누르면 접고, 항목 줄이면 고른다.
        index = (event.y - self._row) // self._row
        self._open = False
        if 0 <= index < len(self._choices):
            value = self._choices[index][0]
            if value != self._value:
                self._value = value
                self._on_change(value)
        self._draw()

    def _draw(self) -> None:
        c = self._canvas
        c.delete("all")
        height = self._row + (self._panel_height() if self._open else 0)
        c.configure(height=height)

        c.create_image(0, 0, image=self._button_photo, anchor="nw")
        c.create_text(
            self._pad, self._row // 2, text=label_for(self._value, self._choices),
            anchor="w", fill=theme.TEXT_LIGHT, font=self._font,
        )
        # ▾. 글리프를 쓰지 않는다 — 글꼴마다 크기와 위치가 달라 단추 안에서 뜬다.
        ax = self._w - self._pad
        ay = self._row // 2
        half = self._arrow // 2
        c.create_polygon(
            ax - self._arrow, ay - half, ax, ay - half, ax - half, ay + half,
            fill=theme.TEXT_DIM,
        )

        if not self._open:
            return

        # **바깥 테두리를 단추와 맞춘다.** 좌우를 테두리 두께만큼 물려서 항목
            # 글자가 길어져도 어긋나지 않는다.
        c.create_image(0, self._row - self._border, image=self._panel(), anchor="nw")
        for index, (value, label) in enumerate(self._choices):
            y = self._row + index * self._row + self._row // 2 - self._border
            c.create_text(
                self._pad, y, text=label, anchor="w",
                fill=theme.GREEN if value == self._value else theme.TEXT_LIGHT,
                font=self._font,
            )
```

- [ ] **Step 4: 테스트를 돌려 통과 확인**

```bash
python -m pytest tests/test_dropdown.py -v
```

- [ ] **Step 5: 커밋**

```bash
git add claude_usage_overlay/dropdown.py tests/test_dropdown.py
git commit -m "feat: 조회 주기 캔버스 드롭다운 추가"
```

---

## Task 12: 설정창

네이티브 `Toplevel`. 크기 조절은 막는다. **닫을 때 한 번에 적용**하고 취소는 없다.
제목 표시줄은 DWM 속성으로 어둡게 한다.

**파일:**
- 생성: `claude_usage_overlay/settings_window.py`
- 수정: `claude_usage_overlay/winmetrics.py` (`dark_title_bar` 추가)
- 테스트: `tests/test_settings_window.py`, `tests/test_winmetrics.py` (추가)

**인터페이스:**
- 사용: `checkbox.Checkbox` (Task 9), `slider.Slider` (Task 10), `dropdown.Dropdown` · `dropdown.POLL_CHOICES` (Task 11), `tray_promote` (Task 7), `autostart.is_enabled/enable/disable` (기존), `config.Config` · `PCT_STEP` · `PCT_MIN` · `PCT_MAX` · `save_config` (Task 3), `winmetrics.dpi_scale` · `dark_title_bar`
- 제공:
  - `winmetrics.dark_title_bar(hwnd: int) -> bool`
  - `settings_window.Draft` — dataclass, 필드 `overlay_visible: bool` · `overlay_detailed: bool` · `poll_seconds: int` · `warn_pct: int` · `danger_pct: int` · `autostart: bool` · `promote: bool`
  - `settings_window.draft_from(cfg: Config, autostart_on: bool, promote_on: bool) -> Draft`
  - `settings_window.commit_draft(draft: Draft, cfg: Config) -> None`
  - `settings_window.warn_bounds() -> tuple[int, int]` · `settings_window.danger_bounds() -> tuple[int, int]`
  - `settings_window.open_settings(root: tk.Tk, config: Config, on_change: Callable[[], None]) -> None`
  - `settings_window.sync_open(config: Config) -> None`

- [ ] **Step 1: 실패하는 테스트 작성 — `tests/test_settings_window.py`**

```python
"""초안 → Config 커밋과 슬라이더 한계. 창을 띄우지 않는다.

**자동 실행과 아이콘 고정은 Config에 들어가지 않는다.** 진짜 상태가 레지스트리에
있으므로, 창을 열 때 거기서 읽어 체크박스를 그리고 닫을 때 거기에 쓴다.
그래서 초안에는 있고 커밋 결과에는 없다 (스펙 4.3절).
"""

from claude_usage_overlay.config import PCT_MAX, PCT_MIN, PCT_STEP, Config
from claude_usage_overlay.settings_window import (
    Draft,
    commit_draft,
    danger_bounds,
    draft_from,
    warn_bounds,
)


def test_the_draft_starts_from_the_live_config():
    cfg = Config(poll_seconds=600, warn_pct=65, danger_pct=85, overlay_visible=False)
    draft = draft_from(cfg, autostart_on=True, promote_on=False)
    assert draft.poll_seconds == 600
    assert (draft.warn_pct, draft.danger_pct) == (65, 85)
    assert draft.overlay_visible is False
    assert draft.autostart is True and draft.promote is False


def test_commit_moves_every_config_field():
    cfg = Config()
    commit_draft(
        Draft(
            overlay_visible=False, overlay_detailed=True, poll_seconds=1800,
            warn_pct=55, danger_pct=95, autostart=True, promote=True,
        ),
        cfg,
    )
    assert (cfg.overlay_visible, cfg.overlay_detailed) == (False, True)
    assert cfg.poll_seconds == 1800
    assert (cfg.warn_pct, cfg.danger_pct) == (55, 95)


def test_commit_does_not_invent_config_fields_for_the_registry_values():
    """autostart·promote가 Config에 새면 파일과 레지스트리가 두 진실이 된다."""
    cfg = Config()
    commit_draft(draft_from(cfg, autostart_on=True, promote_on=True), cfg)
    assert not hasattr(cfg, "autostart")
    assert not hasattr(cfg, "promote")


def test_a_committed_config_survives_a_reload_unchanged(tmp_path):
    """설정창이 쓴 값이 load_config의 보정에 걸리면 닫자마자 값이 바뀐다."""
    from claude_usage_overlay.config import load_config, save_config

    cfg = Config()
    commit_draft(
        Draft(True, False, 1800, PCT_MAX - PCT_STEP, PCT_MAX, False, False), cfg
    )
    path = tmp_path / "config.json"
    save_config(cfg, path)
    after = load_config(path)
    assert (after.warn_pct, after.danger_pct) == (PCT_MAX - PCT_STEP, PCT_MAX)
    assert after.poll_seconds == 1800


def test_a_hand_edited_period_is_committed_as_the_snapped_value():
    """파일에 240초가 적혀 있으면 드롭다운은 5분을 보여준다. 사용자가 그것을
    건드리지 않아도 **닫을 때 300이 저장돼야 한다** — 240이 남으면 화면과 파일이
    갈라지고 다음에 열 때 또 같은 일이 벌어진다 (스펙 4.1절).

    설정창은 위젯을 만든 직후 초안을 위젯이 고른 값으로 맞춘다. 여기서는 그
    맞추기를 nearest()로 재현해 규칙 자체를 잰다.
    """
    from claude_usage_overlay.dropdown import nearest

    cfg = Config(poll_seconds=240)
    draft = draft_from(cfg, autostart_on=False, promote_on=False)
    draft.poll_seconds = nearest(draft.poll_seconds)
    commit_draft(draft, cfg)
    assert cfg.poll_seconds == 300


def test_the_two_sliders_never_overlap():
    """노란은 빨간보다 5%p 아래에서 멈추고 반대도 같다. **서로 밀어내지 않고
    그 자리에 선다** — 밀어내면 한쪽을 끌 때 다른 쪽이 따라와 값이 둘 다 바뀐다."""
    lo, hi = warn_bounds()
    assert (lo, hi) == (PCT_MIN, PCT_MAX - PCT_STEP)
    lo, hi = danger_bounds()
    assert (lo, hi) == (PCT_MIN + PCT_STEP, PCT_MAX)


def test_the_bounds_leave_room_for_the_gap():
    """빨간의 하한이 노란의 하한보다 정확히 한 칸 위여야, 노란을 끝까지 올려도
    빨간이 갈 자리가 남는다."""
    assert danger_bounds()[0] - warn_bounds()[0] == PCT_STEP
    assert danger_bounds()[1] - warn_bounds()[1] == PCT_STEP
```

- [ ] **Step 2: `tests/test_winmetrics.py`에 어두운 제목 표시줄 테스트 추가**

```python
def test_dark_title_bar_succeeds_on_this_windows():
    """DwmSetWindowAttribute(hwnd, 20, TRUE)가 rc=0을 돌려주는지 실제로 본다.
    Windows 10 초기 판올림에는 이 속성이 없어 실패하는데, 그때는 제목 표시줄만
    밝게 뜰 뿐이라 조용히 넘어간다 (스펙 11장)."""
    import tkinter as tk

    from claude_usage_overlay.winmetrics import dark_title_bar

    root = tk.Tk()
    try:
        root.update_idletasks()
        hwnd = int(root.wm_frame(), 16)
        assert dark_title_bar(hwnd) is True
    finally:
        root.destroy()


def test_dark_title_bar_is_quiet_on_a_bogus_handle():
    """실패해도 예외를 던지지 않는다. 여기서 던지면 설정창이 아예 안 열린다."""
    from claude_usage_overlay.winmetrics import dark_title_bar

    assert dark_title_bar(0) is False
```

- [ ] **Step 3: 테스트를 돌려 실패 확인**

```bash
python -m pytest tests/test_settings_window.py tests/test_winmetrics.py -v
```

예상: `ModuleNotFoundError: ... settings_window`와
`ImportError: cannot import name 'dark_title_bar'`.

- [ ] **Step 4: `winmetrics.py`에 `dark_title_bar`를 추가**

상수 블록에 한 줄 더한다.

```python
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
```

`round_window_corners` 뒤에 넣는다.

```python
def dark_title_bar(hwnd: int) -> bool:
    """네이티브 창의 제목 표시줄만 어둡게 만든다. 성공하면 True.

    **무테두리로 직접 그릴 필요가 없다.** 이 속성 하나로 제목 표시줄이 어두워지고
    창 이동·Alt+Tab·스냅·작업 표시줄은 전부 정상으로 남는다 (실측: rc=0, 대조군
    창과 나란히 띄워 육안 확인).

    round_window_corners와 같은 API다. 함수가 하나 늘 뿐이다.

    Windows 10 초기 판올림에는 이 속성이 없어 실패한다. 그때는 제목 표시줄만
    밝은 채로 뜬다 — 보기 나쁠 뿐 동작에는 지장이 없으므로 조용히 넘어간다.
    """
    try:
        value = ctypes.c_int(1)
        rc = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            ctypes.c_uint(DWMWA_USE_IMMERSIVE_DARK_MODE),
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
        return rc == 0
    except (AttributeError, OSError, ValueError, TypeError):
        return False
```

- [ ] **Step 5: `settings_window.py`의 판정 부분을 작성**

```python
"""설정창.

**닫을 때 한 번에 적용하고 취소는 없다.** 닫기 단추·제목줄 ✕·Esc가 모두 같은 일을
한다. 값들이 다시 고르면 그만인 것들이라 취소가 벌어줄 게 없고, ✕만 취소로 두면
실수로 통째로 잃는다.

적용은 공유 Config 객체를 고치는 것으로 끝난다. 폴러·오버레이·트레이가 매 틱 다시
읽으므로 재시작 안내가 필요 없다.

  색 기준     → 다음 다시 그리기 (1초 이내)
  조회 주기   → **다음 폴링 틱부터.** 자고 있는 대기를 깨우지 않는다 — 깨우면
                API를 한 번 더 부르게 되고 그게 429의 원인이다
  자동 실행·아이콘 고정 → 닫을 때 레지스트리에 쓴다. **Config에는 저장하지 않는다**

치수는 배율 100% 기준값이고 전부 dpi_scale()을 곱한다. 글꼴은 음수 픽셀로 준다 —
포인트로 주면 tk scaling이 이미 반영한 배율에 한 번 더 곱해져 150%에서 글자만
창을 넘는다. 오버레이가 겪은 그대로다 (overlay.fonts_for 주석).
"""

import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass
from typing import Callable

from . import autostart, theme, tray_promote
from .checkbox import Checkbox
from .config import PCT_MAX, PCT_MIN, PCT_STEP, Config, save_config
from .dropdown import POLL_CHOICES, Dropdown
from .slider import Slider
from .winmetrics import dark_title_bar, dpi_scale

BASE_WIDTH = 300
PAD = 16          # 창 안쪽 여백
ROW_GAP = 10      # 위젯 줄 사이
INDENT = 24       # 하위 항목 들여쓰기
FONT_PX = 13
HINT_FONT_PX = 11

PROMOTE_HINT_WIN11 = (
    "윈도우 제한으로 바로 반영되지 않습니다 — 다음 로그온부터 적용됩니다.\n"
    "지금 보려면 ∧를 눌러 아이콘을 작업 표시줄로 끌어다 놓으세요."
)
PROMOTE_HINT_WIN10 = (
    "이 윈도우 판올림에서는 프로그램이 고정할 수 없습니다.\n"
    "설정 > 작업 표시줄 > 작업 표시줄에 표시할 아이콘 선택에서 켜세요."
)


@dataclass
class Draft:
    """창이 열려 있는 동안 들고 있는 값. 닫을 때 커밋한다.

    autostart·promote는 **Config에 없는 값**이다. 진짜 상태가 레지스트리에 있으므로
    창을 열 때 거기서 읽고 닫을 때 거기에 쓴다 (스펙 4.3절).
    """

    overlay_visible: bool
    overlay_detailed: bool
    poll_seconds: int
    warn_pct: int
    danger_pct: int
    autostart: bool
    promote: bool


def draft_from(cfg: Config, autostart_on: bool, promote_on: bool) -> Draft:
    return Draft(
        overlay_visible=cfg.overlay_visible,
        overlay_detailed=cfg.overlay_detailed,
        poll_seconds=cfg.poll_seconds,
        warn_pct=cfg.warn_pct,
        danger_pct=cfg.danger_pct,
        autostart=autostart_on,
        promote=promote_on,
    )


def commit_draft(draft: Draft, cfg: Config) -> None:
    """초안을 공유 Config에 옮긴다. **레지스트리는 건드리지 않는다** —
    그쪽은 부작용이 있어서 순수 함수로 두려면 여기서 빠져야 한다."""
    cfg.overlay_visible = draft.overlay_visible
    cfg.overlay_detailed = draft.overlay_detailed
    cfg.poll_seconds = draft.poll_seconds
    cfg.warn_pct = draft.warn_pct
    cfg.danger_pct = draft.danger_pct


def warn_bounds() -> tuple[int, int]:
    """노란 슬라이더가 갈 수 있는 범위.

    상한이 PCT_MAX보다 한 칸 낮은 이유는 빨간이 갈 자리를 남겨야 하기 때문이다.
    실제 상한은 여기에 "빨간 − PCT_STEP"을 한 번 더 씌운 값이고, 그건 빨간이
    움직일 때마다 바뀌므로 위젯이 set_bounds로 갱신한다.
    """
    return (PCT_MIN, PCT_MAX - PCT_STEP)


def danger_bounds() -> tuple[int, int]:
    """빨간 슬라이더가 갈 수 있는 범위. 하한이 노란보다 정확히 한 칸 위다."""
    return (PCT_MIN + PCT_STEP, PCT_MAX)
```

- [ ] **Step 6: 순수 함수만 먼저 통과 확인**

```bash
python -m pytest tests/test_settings_window.py tests/test_winmetrics.py -v
```

예상: 전부 PASS.

- [ ] **Step 7: 창 부분을 같은 파일에 이어 작성**

```python
class SettingsWindow:
    def __init__(self, root: tk.Tk, config: Config, on_change: Callable[[], None]) -> None:
        self._config = config
        self._on_change = on_change
        self._closed = False
        self._scale = s = dpi_scale()

        self._supported = tray_promote.is_supported()
        self._draft = draft_from(
            config,
            autostart_on=autostart.is_enabled(),
            promote_on=tray_promote.is_promoted() if self._supported else False,
        )

        self._win = tk.Toplevel(root)
        self._win.title("Claude 사용량 설정")
        self._win.resizable(False, False)
        self._win.configure(bg=theme.BG)
        self._win.protocol("WM_DELETE_WINDOW", self.close)
        self._win.bind("<Escape>", lambda _e: self.close())

        # 오버레이는 pick_font_family로 고르지만 여기서는 Tk 기본 해석에 맡긴다 —
        # 번들 Pretendard가 이미 올라와 있으므로 이름만 주면 잡히고, 못 잡히면
        # Tk가 조용히 기본 글꼴로 그린다. 창 폭을 아래에서 실제로 재므로
        # 어느 글꼴이 잡혀도 문구가 잘리지 않는다.
        family = "Pretendard"
        self._font = (family, -round(FONT_PX * s))
        self._hint_font = (family, -round(HINT_FONT_PX * s))

        self._body = tk.Frame(self._win, bg=theme.BG)
        self._body.pack(fill="both", expand=True,
                        padx=round(PAD * s), pady=round(PAD * s))
        self._build()
        self._size_to_content()
        self._darken_title_bar()

    # --- 공개 인터페이스 -------------------------------------------------

    def focus(self) -> None:
        self._win.deiconify()
        self._win.lift()
        self._win.focus_force()

    def sync(self) -> None:
        """밖에서 표시·모드가 바뀌었을 때 체크박스를 따라 갱신한다.

        **이게 없으면 닫는 순간 옛 값이 덮어쓴다.** 설정창이 떠 있는 동안 오버레이
        우클릭이나 트레이로 표시를 끄면 체크박스는 켜진 옛 값 그대로이고, 닫으면
        오버레이가 도로 나타난다. overlay_detailed도 똑같다 (스펙 4.4절).

        밖에서 바뀌는 값은 이 둘뿐이다 — 자동 실행과 아이콘 고정은 Config에 없고
        레지스트리가 진짜 상태다.

        트레이 스레드에서도 불릴 수 있으므로 after()로 메인 스레드에 넘긴다.
        """
        if self._closed:
            return
        self._win.after(0, self._sync_now)

    def close(self) -> None:
        """닫기 단추·제목줄 ✕·Esc가 모두 여기로 온다. 취소는 없다."""
        if self._closed:
            return
        self._closed = True

        commit_draft(self._draft, self._config)
        save_config(self._config)

        # 레지스트리는 **닫을 때** 쓴다. 체크하는 순간이 아니다 — 창을 열어보다
        # 만 사람의 시작 프로그램을 바꿔놓으면 안 된다.
        if self._draft.autostart != autostart.is_enabled():
            autostart.enable() if self._draft.autostart else autostart.disable()
        if self._supported and self._draft.promote != tray_promote.is_promoted():
            tray_promote.promote(self._draft.promote)

        self._win.destroy()
        self._on_change()

    # --- 내부 ------------------------------------------------------------

    def _sync_now(self) -> None:
        if self._closed:
            return
        self._draft.overlay_visible = self._config.overlay_visible
        self._draft.overlay_detailed = self._config.overlay_detailed
        self._visible_box.set_checked(self._draft.overlay_visible)
        self._detailed_box.set_checked(self._draft.overlay_detailed)
        self._detailed_box.set_enabled(self._draft.overlay_visible)

    def _darken_title_bar(self) -> None:
        """HWND는 창이 한 번 배치된 뒤에야 유효하므로 update_idletasks가 먼저다."""
        try:
            self._win.update_idletasks()
            hwnd = int(self._win.wm_frame(), 16)
        except (tk.TclError, ValueError):
            return
        dark_title_bar(hwnd)

    def _width(self) -> int:
        """가장 긴 문구에서 역산한다.

        스펙 14장은 300 × 430을 "한국어 문구 길이를 눈대중한 값"으로 남기고
        만들면서 역산하라고 적어뒀다. 상수로 박으면 글꼴이 바뀌거나 문구가
        길어질 때 조용히 잘린다 — 오버레이 창 폭에서 겪은 그대로다.
        """
        base = round(BASE_WIDTH * self._scale)
        font = tkfont.Font(root=self._win, family=self._font[0], size=self._font[1])
        hint = tkfont.Font(root=self._win, family=self._hint_font[0],
                           size=self._hint_font[1])
        widest = 0
        for text in ("작업 표시줄에 트레이 아이콘 고정", "시작할 때 자동 실행",
                     "노란색으로 바뀌는 사용률", "빨간색으로 바뀌는 사용률"):
            widest = max(widest, font.measure(text))
        for line in (PROMOTE_HINT_WIN11 + "\n" + PROMOTE_HINT_WIN10).splitlines():
            widest = max(widest, hint.measure(line) + round(INDENT * self._scale))
        # 체크박스 상자와 여백, 슬라이더 값 글자 자리를 더한다.
        return max(base, widest + round((PAD * 2 + 40) * self._scale))

    def _size_to_content(self) -> None:
        """높이는 내용에서 나온다. 상수로 박으면 문구가 한 줄 늘 때 잘린다."""
        self._win.update_idletasks()
        self._win.geometry(f"{self._width()}x{self._win.winfo_reqheight()}")

    def _separator(self) -> None:
        tk.Frame(self._body, bg=theme.RING_TRACK, height=max(1, round(self._scale))).pack(
            fill="x", pady=round(ROW_GAP * self._scale)
        )

    def _label(self, text: str, font, color: str, indent: int = 0) -> None:
        tk.Label(
            self._body, text=text, font=font, bg=theme.BG, fg=color,
            justify="left", anchor="w",
        ).pack(fill="x", padx=(round(indent * self._scale), 0))

    def _build(self) -> None:
        s = self._scale
        width = self._width() - round(PAD * 2 * s)

        def set_visible(on: bool) -> None:
            self._draft.overlay_visible = on
            # "자세히 보기"는 "오버레이 표시"의 하위 항목이라 표시를 끄면 같이 흐려진다.
            self._detailed_box.set_enabled(on)

        def set_detailed(on: bool) -> None:
            self._draft.overlay_detailed = on

        self._visible_box = Checkbox(
            self._body, "오버레이 표시", self._draft.overlay_visible,
            set_visible, s, self._font, width=width,
        )
        self._visible_box.widget().pack(fill="x")

        self._detailed_box = Checkbox(
            self._body, "자세히 보기", self._draft.overlay_detailed,
            set_detailed, s, self._font, indent=INDENT, width=width,
        )
        self._detailed_box.widget().pack(fill="x")
        self._detailed_box.set_enabled(self._draft.overlay_visible)

        def set_autostart(on: bool) -> None:
            self._draft.autostart = on

        Checkbox(
            self._body, "시작할 때 자동 실행", self._draft.autostart,
            set_autostart, s, self._font, width=width,
        ).widget().pack(fill="x")

        def set_promote(on: bool) -> None:
            self._draft.promote = on

        promote_box = Checkbox(
            self._body, "작업 표시줄에 트레이 아이콘 고정", self._draft.promote,
            set_promote, s, self._font, width=width,
        )
        promote_box.widget().pack(fill="x")
        # 키가 없는 환경(Win10 등)에서는 체크박스가 비활성이고 아무것도 쓰지 않는다.
        promote_box.set_enabled(self._supported)
        self._label(
            PROMOTE_HINT_WIN11 if self._supported else PROMOTE_HINT_WIN10,
            self._hint_font, theme.TEXT_DIM, indent=INDENT,
        )

        self._separator()

        self._label("조회 주기", self._font, theme.TEXT_LIGHT)

        def set_poll(seconds: int) -> None:
            self._draft.poll_seconds = seconds

        poll = Dropdown(
            self._body, POLL_CHOICES, self._draft.poll_seconds, set_poll,
            s, self._font, width=round(110 * s),
        )
        poll.widget().pack(anchor="w", pady=(round(4 * s), 0))
        # **초안을 위젯이 실제로 고른 값으로 맞춘다.** 파일에 손으로 240초를 적어둔
        # 경우 드롭다운은 가장 가까운 5분을 보여주는데, 사용자가 그것을 건드리지
        # 않으면 set_poll이 안 불려 초안에는 240이 남는다. 그러면 화면은 "5분"인데
        # 저장되는 값은 240이 되어 다음에 열 때 또 같은 일이 벌어진다.
        # 슬라이더도 같은 이유로 _apply_slider_bounds가 값을 되받는다.
        self._draft.poll_seconds = poll.value()

        self._label("노란색으로 바뀌는 사용률", self._font, theme.TEXT_LIGHT)
        self._warn = Slider(
            self._body, width, *warn_bounds(), PCT_STEP, self._draft.warn_pct,
            theme.YELLOW, self._set_warn, s, self._font,
        )
        self._warn.widget().pack(fill="x", pady=(0, round(ROW_GAP * s)))

        self._label("빨간색으로 바뀌는 사용률", self._font, theme.TEXT_LIGHT)
        self._danger = Slider(
            self._body, width, *danger_bounds(), PCT_STEP, self._draft.danger_pct,
            theme.RED, self._set_danger, s, self._font,
        )
        self._danger.widget().pack(fill="x")
        self._apply_slider_bounds()

        self._separator()

        row = tk.Frame(self._body, bg=theme.BG)
        row.pack(fill="x")
        tk.Label(
            row, text="닫으면 적용됩니다", font=self._hint_font,
            bg=theme.BG, fg=theme.TEXT_DIM,
        ).pack(side="left")
        tk.Button(
            row, text="닫기", command=self.close, font=self._font,
            bg=theme.RING_TRACK, fg=theme.TEXT_LIGHT,
            activebackground=theme.GREY, activeforeground=theme.TEXT_LIGHT,
            relief="flat", borderwidth=0, padx=round(14 * s), pady=round(4 * s),
        ).pack(side="right")

    def _set_warn(self, value: int) -> None:
        self._draft.warn_pct = value
        self._apply_slider_bounds()

    def _set_danger(self, value: int) -> None:
        self._draft.danger_pct = value
        self._apply_slider_bounds()

    def _apply_slider_bounds(self) -> None:
        """서로를 넘지 않게 상대의 한계를 갱신한다. **밀어내지 않는다** —
        밀어내면 한쪽을 끌 때 다른 쪽이 따라와 값이 둘 다 바뀐다."""
        warn_lo, warn_hi = warn_bounds()
        danger_lo, danger_hi = danger_bounds()
        self._warn.set_bounds(warn_lo, min(warn_hi, self._draft.danger_pct - PCT_STEP))
        self._danger.set_bounds(max(danger_lo, self._draft.warn_pct + PCT_STEP), danger_hi)
        self._draft.warn_pct = self._warn.value()
        self._draft.danger_pct = self._danger.value()


# 열려 있는 창은 하나뿐이다. 두 곳(오버레이 우클릭·트레이 메뉴)에서 열리므로
# 모듈에 붙들어 둔다.
_current: SettingsWindow | None = None


def open_settings(root: tk.Tk, config: Config, on_change: Callable[[], None]) -> None:
    """설정창을 연다. **이미 열려 있으면 새로 만들지 않고 앞으로 끌어온다.**

    tkinter 창 조작은 메인 스레드 몫이다. 트레이(pystray 스레드)에서 부를 때는
    부르는 쪽이 Overlay.schedule로 감싼다 — overlay.py의 after(0, ...)와 같은 방식이다.
    """
    global _current
    if _current is not None and not _current._closed:
        _current.focus()
        return

    def closed() -> None:
        global _current
        _current = None
        on_change()

    _current = SettingsWindow(root, config, closed)


def sync_open(config: Config) -> None:
    """밖에서 overlay_visible·overlay_detailed가 바뀌면 부른다. 안 열려 있으면 무시.

    config는 SettingsWindow가 이미 들고 있으므로 인자로 안 받아도 되지만, 받는
    쪽에서 어떤 값이 바뀌었는지 명시하는 편이 부르는 자리를 읽기 쉽다.
    """
    if _current is not None:
        _current.sync()
```

- [ ] **Step 8: 테스트를 돌려 통과 확인**

```bash
python -m pytest tests/test_settings_window.py tests/test_winmetrics.py -q
```

- [ ] **Step 9: 창을 실제로 띄워 확인**

```bash
python -c "import tkinter as tk; from claude_usage_overlay import font_install; font_install.activate(); from claude_usage_overlay.config import load_config; from claude_usage_overlay.settings_window import open_settings; r=tk.Tk(); r.withdraw(); open_settings(r, load_config(), lambda: r.quit()); r.mainloop()"
```

확인할 것:
- 제목 표시줄이 어둡다
- 문구가 잘리지 않는다 (특히 "작업 표시줄에 트레이 아이콘 고정"과 안내 두 줄)
- "오버레이 표시"를 끄면 "자세히 보기"가 흐려지고 안 눌린다
- 노란 슬라이더를 끝까지 올리면 빨간보다 5%p 아래에서 멈추고 **빨간이 안 움직인다**
- 드롭다운을 펼치면 목록의 좌우 테두리가 단추와 맞는다
- Esc를 누르면 닫힌다

- [ ] **Step 10: 커밋**

```bash
git add claude_usage_overlay/settings_window.py claude_usage_overlay/winmetrics.py tests/test_settings_window.py tests/test_winmetrics.py
git commit -m "feat: 설정창 추가 (닫을 때 일괄 적용, 어두운 제목 표시줄)"
```

---

## Task 13: 우클릭 메뉴와 자세히 모드의 ⚙·✕

**파일:**
- 수정: `claude_usage_overlay/overlay.py`
- 테스트: `tests/test_overlay_modes.py` (추가)

**인터페이스:**
- 사용: `settings_window.open_settings` · `settings_window.sync_open` (Task 12)
- 제공:
  - `overlay.BTN_SIZE: int = 14` · `BTN_TOP: int = 4` · `BTN_GAP: int = 4` · `BTN_RIGHT_MARGIN: int = 4`
  - `overlay.button_rects(width: int, scale: float) -> dict[str, tuple[int, int, int, int]]`
  - `overlay.hit_button(x: int, y: int, rects: dict) -> str | None`
  - `Overlay.open_settings() -> None`

- [ ] **Step 1: 실패하는 테스트 작성 — `tests/test_overlay_modes.py`에 추가**

```python
# --- 자세히 모드의 ⚙·✕ (스펙 3.3절) ---


def test_the_buttons_sit_in_the_top_right_corner():
    rects = ov.button_rects(ov.BASE_WIDTH, 1.0)
    assert set(rects) == {"gear", "close"}
    for x0, y0, x1, y1 in rects.values():
        assert y0 >= 0 and y1 <= ov.BASE_HEIGHT
        assert x1 <= ov.BASE_WIDTH


def test_the_gear_is_left_of_the_close_button():
    """✕가 오른쪽 끝이다. 창의 닫기 단추가 늘 그 자리에 있어 손이 먼저 간다."""
    rects = ov.button_rects(ov.BASE_WIDTH, 1.0)
    assert rects["gear"][2] <= rects["close"][0]


def test_the_buttons_do_not_overlap_the_ring():
    """링은 왼쪽 x 12~54에 있다. 겹치면 단추가 링 위에 얹힌다."""
    rects = ov.button_rects(ov.BASE_WIDTH, 1.0)
    assert min(r[0] for r in rects.values()) > ov.BASE_RING_BOX[2]


def test_the_buttons_do_not_overlap_the_first_text_line():
    """첫 줄은 y 24에 12px 글꼴로 그려져 대략 18~30을 쓴다."""
    rects = ov.button_rects(ov.BASE_WIDTH, 1.0)
    assert max(r[3] for r in rects.values()) <= ov.BASE_LINE1_Y - 6


def test_the_buttons_are_big_enough_to_hit():
    """66px 창의 구석에 넣으면 12px도 안 되어 못 누른다. 자리가 있는 쪽에만 둔다."""
    for x0, y0, x1, y1 in ov.button_rects(ov.BASE_WIDTH, 1.0).values():
        assert x1 - x0 >= 14 and y1 - y0 >= 14


def test_a_press_inside_a_rect_hits_it():
    rects = ov.button_rects(ov.BASE_WIDTH, 1.0)
    x0, y0, x1, y1 = rects["close"]
    assert ov.hit_button((x0 + x1) // 2, (y0 + y1) // 2, rects) == "close"


def test_a_press_outside_hits_nothing():
    rects = ov.button_rects(ov.BASE_WIDTH, 1.0)
    assert ov.hit_button(5, 40, rects) is None
    assert ov.hit_button(ov.BASE_WIDTH - 1, ov.BASE_HEIGHT - 1, rects) is None


def test_the_rects_grow_with_the_scale():
    """배율 150% PC에서 14px 단추는 21px이 되어야 손가락 크기가 같아 보인다."""
    small = ov.button_rects(round(ov.BASE_WIDTH * 1.0), 1.0)["close"]
    big = ov.button_rects(round(ov.BASE_WIDTH * 1.5), 1.5)["close"]
    assert (big[2] - big[0]) == round(ov.BTN_SIZE * 1.5)
    assert (small[2] - small[0]) == ov.BTN_SIZE


def test_the_rects_stay_pinned_to_the_right_edge_at_every_scale():
    for scale in (1.0, 1.25, 1.5):
        width = round(ov.BASE_WIDTH * scale)
        rects = ov.button_rects(width, scale)
        assert rects["close"][2] == width - round(ov.BTN_RIGHT_MARGIN * scale)
```

- [ ] **Step 2: 테스트를 돌려 실패 확인**

```bash
python -m pytest tests/test_overlay_modes.py -v -k button
```

예상: `AttributeError: ... has no attribute 'button_rects'`.

- [ ] **Step 3: `overlay.py`에 상수와 순수 함수를 추가**

`DRAG_THRESHOLD` 뒤에 넣는다.

```python
# 자세히 모드 우상단의 ⚙·✕. **기본 모드에는 없다** — 66px 창의 구석에 넣으면
# 12px도 안 되어 못 누른다. 단추는 자리가 있는 쪽에만 둔다.
BTN_SIZE = 14
BTN_TOP = 4
BTN_GAP = 4
BTN_RIGHT_MARGIN = 4
```

`is_drag` 뒤에 넣는다.

```python
def button_rects(width: int, scale: float) -> dict[str, tuple[int, int, int, int]]:
    """⚙·✕의 판정 상자. width는 **배율이 곱해진** 창 폭이다.

    ✕를 오른쪽 끝에 둔다. 창의 닫기 단추가 늘 그 자리에 있어 손이 먼저 간다.
    """
    size = round(BTN_SIZE * scale)
    top = round(BTN_TOP * scale)
    gap = round(BTN_GAP * scale)
    right = width - round(BTN_RIGHT_MARGIN * scale)
    close_x0 = right - size
    gear_x0 = close_x0 - gap - size
    return {
        "gear": (gear_x0, top, gear_x0 + size, top + size),
        "close": (close_x0, top, close_x0 + size, top + size),
    }


def hit_button(x: int, y: int, rects: dict[str, tuple[int, int, int, int]]) -> str | None:
    """누른 자리가 단추 안인지.

    캔버스 아이템에 tag_bind를 걸지 않는다. 캔버스를 1초마다 통째로 다시 그리므로
    매번 다시 걸어야 하고, 그러면 창 전체의 <Button-1> 바인딩과 순서를 다투게 된다.
    좌표로 판정하면 순수 함수라 테스트도 된다.
    """
    for name, (x0, y0, x1, y1) in rects.items():
        if x0 <= x <= x1 and y0 <= y <= y1:
            return name
    return None
```

- [ ] **Step 4: 마우스 처리에 단추와 우클릭을 붙인다**

import에 `settings_window`를 추가한다. `settings_window`는 `overlay`를 import하지
않으므로 순환이 없다.

```python
from . import font_install, settings_window, text_center, theme
```

`__init__`의 바인딩 블록에 셋을 더한다.

```python
        self._buttons = button_rects(self._detail.w, self._scale)
        self._hover = False
        self._pressed: str | None = None
        for widget in (self._win, self._canvas):
            widget.bind("<Button-1>", self._on_press)
            widget.bind("<B1-Motion>", self._on_drag)
            widget.bind("<ButtonRelease-1>", self._on_release)
            widget.bind("<Button-3>", self._on_menu)
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)
```

`_on_press`에 한 줄, `_on_release`를 전체 교체한다.

```python
    def _on_press(self, event) -> None:
        self._drag["x"] = event.x_root - self._win.winfo_x()
        self._drag["y"] = event.y_root - self._win.winfo_y()
        self._drag["ox"] = event.x_root
        self._drag["oy"] = event.y_root
        self._drag["moved"] = False
        self._pressed = (
            hit_button(event.x, event.y, self._buttons)
            if self._detailed and self._hover
            else None
        )

    def _on_release(self, event) -> None:
        """3px 안에서 뗐으면 클릭이다.

        단추를 누르고 있었으면 단추 동작이 이긴다. 그러지 않으면 ⚙를 눌렀을 때
        전환까지 함께 일어난다.
        """
        pressed, self._pressed = self._pressed, None
        if self._drag["moved"]:
            return
        if pressed == "gear":
            self.open_settings()
            return
        if pressed == "close":
            self.hide()
            return
        # **자세히 모드에는 좌클릭 전환이 없다.** 아래 줄에 이미 카운트다운이 있다.
        if self._detailed:
            return
        self._show_time = not self._show_time
        self._redraw()

    def _on_enter(self, _event) -> None:
        self._hover = True
        self._redraw()

    def _on_leave(self, _event) -> None:
        self._hover = False
        self._redraw()
```

- [ ] **Step 5: 우클릭 메뉴와 설정창 열기를 추가**

`schedule` 뒤에 넣는다.

```python
    def open_settings(self) -> None:
        """설정창을 연다. 이 메서드는 **메인 스레드에서만** 부른다.

        트레이 메뉴는 pystray 스레드에서 도므로 schedule(overlay.open_settings)로
        감싸서 부른다.
        """
        settings_window.open_settings(
            self._root, self._config, on_change=self.apply_config
        )

    def _on_menu(self, event) -> None:
        """우클릭 메뉴. 양쪽 모드가 같다.

        가운데 항목은 **문구가 바뀌는 토글**이라 자세히 모드에서는 `기본 보기`가
        된다. 트레이의 `오버레이 보이기 / 숨기기`와 같은 방식이므로 체크 표시를
        쓰지 않는다 — 체크가 붙으면 "이 항목을 켠다"로 읽혀서, 지금 무엇을 보고
        있는지와 무엇으로 바뀌는지가 헷갈린다.
        """
        menu = tk.Menu(self._win, tearoff=0, bg=theme.BG, fg=theme.TEXT_LIGHT,
                       activebackground=theme.RING_TRACK,
                       activeforeground=theme.TEXT_LIGHT, borderwidth=0)
        menu.add_command(label="설정…", command=self.open_settings)
        menu.add_command(
            label="기본 보기" if self._detailed else "자세히 보기",
            command=lambda: self.set_detailed(not self._detailed),
        )
        menu.add_separator()
        menu.add_command(label="오버레이 숨기기", command=self.hide)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            # grab_release가 없으면 메뉴를 Esc로 닫은 뒤 마우스가 잠긴다.
            menu.grab_release()
```

- [ ] **Step 6: 밖에서 값이 바뀌면 열려 있는 설정창을 갱신한다**

`_set_visible`과 `set_detailed`의 끝에 한 줄씩 더한다. **여기가 스펙 4.4절의
함정을 막는 자리다** — 이 줄이 없으면 설정창이 떠 있는 동안 우클릭으로 숨긴
오버레이가 창을 닫는 순간 도로 나타난다.

```python
    def _set_visible(self, visible: bool) -> None:
        self._visible = visible
        self._config.overlay_visible = visible
        save_config(self._config)
        self._win.after(0, self._win.deiconify if visible else self._win.withdraw)
        # 설정창이 떠 있으면 체크박스를 따라 갱신한다 (스펙 4.4절).
        settings_window.sync_open(self._config)
```

`set_detailed`에도 같은 줄을 마지막에 넣는다.

**`apply_config`가 이것과 부딪히지 않는지 확인한다.** 설정창이 닫히면
`on_change` → `apply_config` → `_set_visible` → `sync_open`이 되는데, 그때
`_current`는 이미 `None`이므로(`open_settings`의 `closed()`가 먼저 비운다)
`sync_open`이 아무 일도 하지 않는다. 순서가 이 방향이어야 한다.

- [ ] **Step 7: 자세히 모드에서 마우스를 올리면 단추를 그린다**

`_redraw_detailed`의 마지막(`_draw_text` 호출 뒤)에 넣는다.

```python
        if self._hover:
            self._draw_buttons()
```

`_draw_text` 뒤에 메서드 둘을 추가한다.

```python
    def _draw_buttons(self) -> None:
        """⚙와 ✕를 직접 그린다.

        글리프(`⚙`·`✕`)를 쓰지 않는다. Pretendard에 ⚙(U+2699)가 없어 Tk가 다른
        글꼴로 대체하는데, 어느 글꼴이 잡히느냐에 따라 크기와 위치가 달라져 단추
        안에서 뜬다. 없으면 빈 사각형이 그려진다. icon_render._cross_icon이 ✕를
        선으로 긋는 것과 같은 판단이다.
        """
        for name, (x0, y0, x1, y1) in self._buttons.items():
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            r = (x1 - x0) / 2
            if name == "close":
                pad = r * 0.45
                for a, b in (((-1, -1), (1, 1)), ((1, -1), (-1, 1))):
                    self._canvas.create_line(
                        cx + a[0] * pad, cy + a[1] * pad,
                        cx + b[0] * pad, cy + b[1] * pad,
                        fill=theme.TEXT_DIM, width=max(1, round(1.5 * self._scale)),
                        capstyle="round",
                    )
            else:
                self._draw_gear(cx, cy, r)

    def _draw_gear(self, cx: float, cy: float, r: float) -> None:
        """원 하나에 살 여섯. 14px에서 톱니를 그리면 뭉개져 점으로 보인다."""
        import math

        width = max(1, round(1.5 * self._scale))
        ring = r * 0.42
        self._canvas.create_oval(
            cx - ring, cy - ring, cx + ring, cy + ring,
            outline=theme.TEXT_DIM, width=width,
        )
        for index in range(6):
            angle = math.pi * index / 3
            dx, dy = math.cos(angle), math.sin(angle)
            self._canvas.create_line(
                cx + dx * ring, cy + dy * ring,
                cx + dx * r * 0.95, cy + dy * r * 0.95,
                fill=theme.TEXT_DIM, width=width, capstyle="round",
            )
```

`import math`는 파일 상단으로 올린다 — 함수 안 import는 1초마다 도는 경로에 있다.

- [ ] **Step 8: 테스트를 돌려 통과 확인**

```bash
python -m pytest tests/test_overlay_modes.py -v
```

- [ ] **Step 9: 실제로 눌러서 확인**

```bash
python -m claude_usage_overlay
```

확인할 것:
- 우클릭 → `설정… / 자세히 보기 / ─ / 오버레이 숨기기`
- `자세히 보기`를 누르면 창이 커지고 **오른쪽 아래 모서리가 제자리에 남는다**
- 자세히 모드에서 우클릭하면 가운데 항목이 `기본 보기`로 바뀌어 있다
- 자세히 모드에 마우스를 올리면 우상단에 ⚙·✕가 나타난다
- ⚙를 누르면 설정창이 열리고, 그 상태로 오버레이를 우클릭해 숨긴 뒤 설정창을
  닫으면 **오버레이가 도로 나타나지 않는다** (스펙 4.4절)
- ✕를 누르면 숨겨지고 트레이는 살아 있다. 풍선 알림이 뜨지 않는다
- 창을 왼쪽 끝으로 끌어다 놓고 자세히로 바꾸면 화면 밖으로 나가지 않는다

- [ ] **Step 10: 커밋**

```bash
git add claude_usage_overlay/overlay.py tests/test_overlay_modes.py
git commit -m "feat: 오버레이 우클릭 메뉴와 자세히 모드 ⚙·✕ 단추 추가"
```

---

## Task 14: 첫 실행 안내창

`config.json`이 없을 때 한 번 뜬다. 작업 표시줄을 흉내 낸 도식을 도형으로 그린다 —
스크린샷 파일을 끼워 넣지 않으므로 exe가 안 커지고 배율도 따라간다.

**파일:**
- 생성: `claude_usage_overlay/first_run.py`
- 테스트: `tests/test_first_run.py`

**인터페이스:**
- 사용: `config.config_path` · `Config` · `save_config` (Task 3), `tray_promote.is_supported` (Task 7), `winmetrics.dpi_scale` · `dark_title_bar` (Task 12)
- 제공:
  - `first_run.is_first_run(path: Path | None = None) -> bool`
  - `first_run.LAST_LINE_WIN11: str` · `first_run.LAST_LINE_WIN10: str`
  - `first_run.last_line(supported: bool) -> str`
  - `first_run.show_intro(root: tk.Tk, config: Config, supported: bool) -> None`

- [ ] **Step 1: 실패하는 테스트 작성 — `tests/test_first_run.py`**

```python
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


def test_show_intro_saves_the_live_config_not_a_fresh_one(monkeypatch):
    """새 Config()를 저장하면 안내창이 뜨기 전에 오버레이가 이미 저장한 값을 덮는다.

    **이 테스트만 창을 만든다.** 검증하려는 것이 "창을 띄우는 경로가 어떤 객체를
    저장하는가"라서 그 경로를 실제로 지나야 한다. root를 withdraw하므로 안내창만
    잠깐 떴다 사라지고, save_config를 가로채므로 디스크에는 쓰지 않는다.
    """
    import tkinter as tk

    from claude_usage_overlay.config import Config

    saved = []
    monkeypatch.setattr(first_run, "save_config", saved.append)

    cfg = Config(overlay_visible=False)
    root = tk.Tk()
    root.withdraw()
    try:
        first_run.show_intro(root, cfg, supported=True)
    finally:
        root.destroy()

    assert saved == [cfg], "살아 있는 Config를 그대로 저장해야 한다"
    assert saved[0].overlay_visible is False
```

- [ ] **Step 2: 테스트를 돌려 실패 확인**

```bash
python -m pytest tests/test_first_run.py -v
```

- [ ] **Step 3: `first_run.py` 작성**

```python
"""첫 실행 판정과 안내창.

**첫 실행인지는 기동할 때 한 번만 판정해 불리언으로 들고 다닌다.** 5장의 자동
IsPromoted도 "config.json이 없으면"을 조건으로 삼는데, 그쪽은 아이콘이 뜨기를
기다렸다가 별도 스레드에서 늦게 실행된다. 둘이 각자 파일을 확인하면 안내창이
먼저 저장해 버려서 자동 시도가 영영 돌지 않는다. 그래서 판정은 __main__이 한 번만
하고 이 모듈은 그 결과를 받는다.

**안내창을 띄우는 즉시 config.json을 기본값으로 저장한다.** 그러지 않으면 사용자가
아무 설정도 건드리지 않는 한 매 실행마다 뜬다.

도식은 도형으로 그린다. 스크린샷 파일을 끼워 넣으면 exe가 커지고 배율도 안 따라간다.
"""

import tkinter as tk
from pathlib import Path

from . import theme
from .config import Config, config_path, save_config
from .winmetrics import dark_title_bar, dpi_scale

TITLE = "Claude 사용량 — 처음 실행"

HEADING = "트레이 아이콘을 작업 표시줄에 꺼내 두면 편합니다"
BODY = (
    "사용량은 작업 표시줄 오른쪽 트레이 아이콘에 늘 보입니다.\n"
    "숨은 아이콘 안에 들어가 있으면 ∧를 눌러 꺼낼 수 있습니다."
)

LAST_LINE_WIN11 = "지금 안 하셔도 됩니다. 다음 로그온부터는 저절로 나옵니다."
LAST_LINE_WIN10 = (
    "설정 > 작업 표시줄 > 작업 표시줄에 표시할 아이콘 선택에서 켜도 됩니다."
)

BASE_WIDTH = 380
PAD = 18
FONT_PX = 13
HEADING_PX = 15
HINT_PX = 11
DIAGRAM_H = 96


def is_first_run(path: Path | None = None) -> bool:
    """config.json이 없으면 첫 실행이다.

    깨진 파일도 "한 번 켠 적이 있다"는 증거로 본다. 내용을 읽어 판정하면 오타 하나에
    안내창이 매 실행마다 뜬다.
    """
    return not (path or config_path()).exists()


def last_line(supported: bool) -> str:
    """마지막 줄만 OS로 갈린다.

    Win11에서는 첫 실행에 IsPromoted=1을 써두므로 "다음 로그온부터 저절로 나온다"가
    참이다. Win10에서는 우리가 써둘 값이 없으므로 그 약속을 할 수 없다.

    **스펙 14장의 미해결 항목이 여기에 걸려 있다.** IsPromoted가 다음 로그온에
    실제로 반영되는지 확인되지 않았고, 안 되면 이 문구가 거짓이 된다.
    Step 6의 확인 절차를 보라.
    """
    return LAST_LINE_WIN11 if supported else LAST_LINE_WIN10


def show_intro(root: tk.Tk, config: Config, supported: bool) -> None:
    """안내창을 띄우고 config.json을 저장한다.

    **띄우는 즉시 저장한다.** 그러지 않으면 사용자가 아무 설정도 건드리지 않는 한
    매 실행마다 뜬다.

    새 Config()가 아니라 **살아 있는 것**을 저장한다. 안내창이 뜨기 전에 오버레이가
    이미 저장한 값(예: ✕를 눌러 숨긴 상태)이 있으면 그것을 덮으면 안 된다.
    """
    save_config(config)

    s = dpi_scale()
    win = tk.Toplevel(root)
    win.title(TITLE)
    win.resizable(False, False)
    win.configure(bg=theme.BG)
    win.bind("<Escape>", lambda _e: win.destroy())

    body = tk.Frame(win, bg=theme.BG)
    body.pack(fill="both", expand=True, padx=round(PAD * s), pady=round(PAD * s))

    def label(text: str, px: int, color: str) -> None:
        tk.Label(
            body, text=text, bg=theme.BG, fg=color, justify="left", anchor="w",
            font=("Pretendard", -round(px * s)),
        ).pack(fill="x", pady=(0, round(6 * s)))

    label(HEADING, HEADING_PX, theme.TEXT_LIGHT)
    _draw_diagram(body, s)
    label(BODY, FONT_PX, theme.TEXT_LIGHT)
    label(last_line(supported), HINT_PX, theme.TEXT_DIM)

    tk.Button(
        body, text="알겠습니다", command=win.destroy,
        font=("Pretendard", -round(FONT_PX * s)),
        bg=theme.RING_TRACK, fg=theme.TEXT_LIGHT,
        activebackground=theme.GREY, activeforeground=theme.TEXT_LIGHT,
        relief="flat", borderwidth=0, padx=round(14 * s), pady=round(4 * s),
    ).pack(anchor="e")

    win.update_idletasks()
    win.geometry(f"{round(BASE_WIDTH * s)}x{win.winfo_reqheight()}")
    try:
        dark_title_bar(int(win.wm_frame(), 16))
    except (tk.TclError, ValueError):
        pass


def _draw_diagram(parent: tk.Misc, s: float) -> None:
    """작업 표시줄과 숨은 아이콘 팝업, 그리고 끄는 방향.

    도형만 쓴다. 그려지는 것은 이렇다 —

        ┌──────────┐          ← 숨은 아이콘 팝업 (아이콘 셋)
        └────┬─────┘
        ═════╧═══[∧][icon]═   ← 작업 표시줄. ∧ 오른쪽이 트레이다
              └──→ 화살표가 팝업에서 표시줄 쪽을 가리킨다
    """
    w = round((BASE_WIDTH - PAD * 2) * s)
    h = round(DIAGRAM_H * s)
    canvas = tk.Canvas(parent, width=w, height=h, bg=theme.BG, highlightthickness=0)
    canvas.pack(fill="x", pady=(0, round(10 * s)))

    bar_h = round(22 * s)
    bar_y = h - bar_h
    canvas.create_rectangle(0, bar_y, w, h, fill=theme.RING_TRACK, outline="")

    # ∧와 그 오른쪽의 트레이 아이콘 둘.
    chevron_x = w - round(96 * s)
    mid = bar_y + bar_h / 2
    tip = round(4 * s)
    canvas.create_line(
        chevron_x - tip, mid + tip / 2, chevron_x, mid - tip / 2,
        chevron_x + tip, mid + tip / 2,
        fill=theme.TEXT_LIGHT, width=max(1, round(1.5 * s)),
        capstyle="round", joinstyle="round",
    )
    icon = round(12 * s)
    for index, color in enumerate((theme.GREY, theme.FILL_GREEN)):
        x = chevron_x + round((22 + index * 20) * s)
        canvas.create_rectangle(
            x, mid - icon / 2, x + icon, mid + icon / 2, fill=color, outline=""
        )

    # 숨은 아이콘 팝업. ∧ 위에 뜬다.
    pop_w, pop_h = round(84 * s), round(34 * s)
    pop_x = chevron_x - pop_w // 2
    pop_y = bar_y - pop_h - round(16 * s)
    canvas.create_rectangle(
        pop_x, pop_y, pop_x + pop_w, pop_y + pop_h,
        fill=theme.BG, outline=theme.TEXT_DIM,
    )
    for index in range(3):
        x = pop_x + round((12 + index * 22) * s)
        y = pop_y + pop_h / 2
        color = theme.FILL_GREEN if index == 1 else theme.GREY
        canvas.create_rectangle(
            x, y - icon / 2, x + icon, y + icon / 2, fill=color, outline=""
        )

    # 팝업의 아이콘에서 표시줄 트레이로 향하는 화살표. 끄는 방향이 이 그림의 요점이다.
    start = (pop_x + round(26 * s) + icon / 2, pop_y + pop_h)
    end = (chevron_x + round(46 * s), mid - icon / 2 - round(3 * s))
    canvas.create_line(
        *start, start[0], end[1] - round(10 * s), *end,
        fill=theme.GREEN, width=max(1, round(1.5 * s)),
        arrow="last", arrowshape=(round(8 * s), round(10 * s), round(4 * s)),
        smooth=True,
    )
```

- [ ] **Step 4: 테스트를 돌려 통과 확인**

```bash
python -m pytest tests/test_first_run.py -v
```

- [ ] **Step 5: 안내창을 띄워 확인**

```bash
python -c "import tkinter as tk; from claude_usage_overlay import font_install, first_run; font_install.activate(); r=tk.Tk(); r.withdraw(); first_run.show_intro(r, supported=True); r.mainloop()"
```

**주의:** 이 명령은 `%APPDATA%\claude-usage-overlay\config.json`을 기본값으로
덮어쓴다. 지금 쓰는 설정이 있으면 먼저 복사해 두고, 확인이 끝나면 되돌린다.

도식에서 ∧의 위치와 끄는 방향이 읽히는지, 문구가 잘리지 않는지 본다.

- [ ] **Step 6: 스펙 14장의 미해결 항목을 확인한다**

`IsPromoted`가 **다음 로그온에 실제로 반영되는지** 확인되지 않았다. 확인 절차:

```bash
python -c "from claude_usage_overlay import tray_promote as t; print('지원', t.is_supported()); print('썼나', t.promote(True, 'pythonw.exe')); print('읽으니', t.is_promoted('pythonw.exe'))"
```

셋 다 `True`가 나오면 값이 놓인 것이다. 그 상태로 **로그오프 → 로그인**한 뒤

```bash
pythonw -m claude_usage_overlay
```

로 띄워, **끌어내지 않아도 트레이 아이콘이 작업 표시줄에 바로 보이는지** 본다.

- 보이면 `LAST_LINE_WIN11`이 참이다. 그대로 둔다
- **안 보이면** 이 기능을 빼고 안내창만 남긴다. 고칠 곳이 셋이다
  1. `first_run.LAST_LINE_WIN11`을 `LAST_LINE_WIN10`과 같은 내용(윈도우 설정에서
     켜라는 안내)으로 바꾼다 — "다음 로그온부터는 저절로 나옵니다"가 거짓이 되기 때문이다
  2. `__main__`의 첫 실행 자동 `promote_when_ready` 호출을 지운다 (Task 15 Step 4)
  3. `settings_window.PROMOTE_HINT_WIN11`의 첫 줄도 같은 이유로 고친다.
     체크박스 자체는 남긴다 — 사용자가 직접 켜는 것은 여전히 유효한 조작이고,
     레지스트리 값이 언젠가 반영될 수도 있다

`is_supported()`가 `False`면 이 PC가 Windows 11이 아니거나 키가 없는 것이다.
그때는 확인을 건너뛰고 `LAST_LINE_WIN10` 경로만 쓴다.

- [ ] **Step 7: 커밋**

```bash
git add claude_usage_overlay/first_run.py tests/test_first_run.py
git commit -m "feat: 첫 실행 안내창과 작업 표시줄 도식 추가"
```

---

## Task 15: 배선 — 트레이 메뉴 · 진입점 · README

**파일:**
- 수정: `claude_usage_overlay/tray.py`, `claude_usage_overlay/__main__.py`, `README.md`
- 테스트: `tests/test_tray.py` (추가)

**인터페이스:**
- 사용: `Overlay.schedule` · `Overlay.open_settings` · `Overlay.is_detailed` · `Overlay.set_detailed` (Task 5·13), `first_run.is_first_run` · `first_run.show_intro` (Task 14), `tray_promote.is_supported` · `promote_when_ready` (Task 7)

- [ ] **Step 1: 실패하는 테스트 작성 — `tests/test_tray.py`에 추가**

```python
def test_the_tooltip_starts_with_the_prefix_tray_promote_looks_for():
    """tray_promote는 InitialTooltip이 이 접두사로 시작하는 항목을 우리 것으로
    고른다. 여기 첫 줄을 고치면 아이콘 고정이 아무 표시 없이 죽는다."""
    from claude_usage_overlay.tray_promote import TOOLTIP_PREFIX

    for s in (
        state(),
        state(Status.STALE),
        HudState(Status.RELOGIN, None, "재로그인 필요 — claude auth login"),
        HudState(Status.STALE, None, "불러오는 중"),
    ):
        assert _tooltip(s).startswith(TOOLTIP_PREFIX), _tooltip(s)


def test_the_menu_has_no_config_file_item():
    """설정창이 대신하므로 "설정 파일 열기"가 사라졌다. 남아 있으면 사용자가
    파일을 열어 고치고, 설정창이 닫힐 때 전체 쓰기로 그 편집을 덮는다."""
    import claude_usage_overlay.tray as tray_mod

    source = Path(tray_mod.__file__).read_text(encoding="utf-8")
    assert "설정 파일 열기" not in source
    assert "notepad" not in source
    assert "Pretendard 글꼴 설치" not in source
```

`tests/test_tray.py` 상단 import에 `from pathlib import Path`를 추가한다.

- [ ] **Step 2: 테스트를 돌려 실패 확인**

```bash
python -m pytest tests/test_tray.py -v
```

예상: `test_the_menu_has_no_config_file_item`이 FAIL (아직 `_open_config`가 있다).
`test_the_tooltip_starts_with...`는 이미 통과한다 — 그게 이 테스트의 목적이다.
지금 참인 것을 앞으로도 참으로 묶어두는 관문이다.

- [ ] **Step 3: `tray.py`의 메뉴를 개편한다**

import에서 `subprocess`와 `config_path`·`save_config`를 지운다. Task 1에서
`font_install`과 `threading`은 이미 지웠다.

```python
import os
from datetime import datetime, timezone

import pystray

from . import autostart
from .config import Config
from .formatting import LOADING_TEXT, format_age, format_countdown
from .icon_render import render_icon
from .models import HudState, Status
from .winmetrics import system_icon_size
```

`_build_menu`를 바꾼다.

```python
    def _build_menu(self) -> pystray.Menu:
        """스펙 9장의 순서 그대로.

        "설정 파일 열기"는 설정창이 대신하므로 뺐다. 자동 실행이 트레이와 설정창
        양쪽에 있지만 둘 다 레지스트리를 읽어 그리므로 어긋나지 않는다.
        """
        return pystray.Menu(
            pystray.MenuItem(
                lambda _: "오버레이 숨기기" if self._overlay.is_visible() else "오버레이 보이기",
                self._toggle_overlay,
            ),
            pystray.MenuItem("지금 갱신", self._refresh_now),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("설정…", self._open_settings),
            pystray.MenuItem(
                "시작할 때 자동 실행",
                self._toggle_autostart,
                checked=lambda _: autostart.is_enabled(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("종료", self._quit),
        )
```

`_open_config`(195-200행)를 지우고 그 자리에 넣는다.

```python
    def _open_settings(self) -> None:
        """**pystray 스레드에서 불린다.** tkinter 창 조작은 메인 스레드 몫이므로
        오버레이의 위젯 after()로 넘긴다 — overlay._set_visible과 같은 방식이다."""
        self._overlay.schedule(self._overlay.open_settings)
```

- [ ] **Step 4: `__main__.py`를 배선한다**

```python
"""진입점.

스레드 배치:
  메인 스레드   tkinter (오버레이·설정창) + 1초마다 상태 펌프
  폴러 스레드   5분마다 API 조회
  트레이 스레드 pystray 이벤트 루프
  (첫 실행에 한 번) 아이콘 고정 스레드

tkinter 창 조작은 메인 스레드에서만 한다. 폴러는 잠금으로 보호된 state()만
노출하고, 트레이 메뉴는 Overlay가 after()로 넘겨준 것만 창에 반영시킨다.
"""

import threading
import tkinter as tk

from . import first_run, font_install, tray_promote
from .config import load_config
from .credentials import CredentialStore
from .overlay import Overlay
from .poller import Poller
from .tray import Tray
from .winmetrics import enable_dpi_awareness

PUMP_INTERVAL_MS = 1000


def main() -> None:
    # Tk()보다 먼저 불러야 한다. 이걸 빠뜨리면 Windows가 창을 비트맵 확대하고
    # 그 위에 Overlay가 dpi_scale()을 또 곱해 배율의 제곱만큼 커진다.
    enable_dpi_awareness()

    # 번들 Pretendard를 이 프로세스에 올린다. 이것도 Tk()보다 먼저다 —
    # Tk는 시작할 때 글꼴 목록을 읽으므로, 나중에 올리면 이번 실행에서는 못 쓴다.
    font_install.activate()

    # **첫 실행인지는 여기서 한 번만 판정한다.** 안내창이 config.json을 저장하고
    # 아이콘 고정 스레드는 아이콘이 뜬 뒤에야 도는데, 둘이 각자 파일을 확인하면
    # 안내창이 먼저 저장해 버려 자동 시도가 영영 돌지 않는다.
    first = first_run.is_first_run()

    config = load_config()

    poller = Poller(store=CredentialStore(), config=config)
    poller.start()

    root = tk.Tk()
    root.withdraw()  # 보이지 않는 루트. 실제 창은 Overlay가 만드는 Toplevel이다

    overlay = Overlay(root, config)
    tray = Tray(poller, overlay, config)

    threading.Thread(target=tray.run, daemon=True).start()

    if first:
        first_run.show_intro(root, config, supported=tray_promote.is_supported())
        # **첫 실행 1회만 자동으로 써둔다.** 이후로는 건드리지 않는다 — 나중에
        # 직접 숨긴 사람과 싸우지 않기 위해서다.
        #
        # 별도 스레드인 이유는 항목이 아이콘이 한 번 뜬 뒤에야 생기기 때문이다.
        # 여기서 기다리면 mainloop가 시작되지 않아 창이 아예 안 뜬다.
        threading.Thread(target=tray_promote.promote_when_ready, daemon=True).start()

    def pump() -> None:
        try:
            state = poller.state()
            overlay.update(state)
            tray.refresh_icon()
        finally:
            # 재예약을 finally에 둔다. 이 줄에 도달하지 못하면 다음 after가
            # 안 걸리고 상태 갱신이 **영구히** 멈춘다 — 오버레이는 자기 _tick으로
            # 계속 그리므로 화면은 살아 있는 채 값만 얼어붙고, pythonw에는
            # 콘솔이 없어 아무도 원인을 못 본다.
            root.after(PUMP_INTERVAL_MS, pump)

    root.after(PUMP_INTERVAL_MS, pump)
    root.mainloop()


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 전체 테스트**

```bash
python -m pytest -q
```

예상: 실패 0.

- [ ] **Step 6: README를 고친다**

`## 글꼴` 절(42-59행)을 바꾼다. **삭제 안내는 남긴다** — 예전 판올림으로 계정
글꼴 폴더에 설치한 사람의 잔여물을 치울 방법을 아는 사람이 없어지면 안 된다.

```markdown
## 글꼴

화면 문구는 **Pretendard**로 그린다. 윈도우 기본 글꼴인 Segoe UI에는 한글 글리프가
없어서, 그대로 두면 숫자·영문과 한글이 서로 다른 글꼴로 섞여 나오기 때문이다.

**글꼴이 프로그램 안에 들어 있다.** 받을 것도 설치할 것도 없고 첫 실행부터
Pretendard다. 계정 글꼴 폴더에도 레지스트리에도 쓰지 않는다. 라이선스는
SIL OFL 1.1이고 `claude_usage_overlay/fonts/OFL.txt`에 함께 들어 있다.

### 예전 판올림으로 설치했던 경우

트레이 메뉴의 "Pretendard 글꼴 설치"로 깔았던 사용자에게는 계정 글꼴 폴더에
TTF 둘(5.4MB)과 레지스트리 값 둘이 남는다. 이제 아무도 안 보는 찌꺼기다.

**프로그램이 지우지는 않는다.** 값 이름도 파일 경로도 사용자가 손으로 설치한 것과
구별되지 않아서, 지우면 다른 용도로 Pretendard를 쓰던 사람의 글꼴을 뺏는다.
같은 이름이 두 벌 올라오는 것은 무해하다.

직접 치우려면 아래 폴더의 `Pretendard-Regular.ttf`·`Pretendard-Bold.ttf`를 삭제하고,

```
%LOCALAPPDATA%\Microsoft\Windows\Fonts
```

레지스트리 `HKCU\Software\Microsoft\Windows NT\CurrentVersion\Fonts`에서
`Pretendard Regular (TrueType)`·`Pretendard Bold (TrueType)` 값을 지운다.
```

`## 설정` 절(61-76행)을 바꾼다.

```markdown
## 설정

트레이 메뉴나 오버레이 우클릭의 **설정…** 으로 연다. 값은 **창을 닫을 때 한 번에**
적용되고 취소는 없다. 색 기준은 1초 안에, 조회 주기는 다음 조회부터 반영된다.

| 항목 | 기본값 | 설명 |
|---|---|---|
| 오버레이 표시 | 켜짐 | 끄면 트레이 아이콘만 남는다 |
| └ 자세히 보기 | 꺼짐 | 켜면 카운트다운과 갱신 문구가 함께 보인다 |
| 시작할 때 자동 실행 | 꺼짐 | 레지스트리 `HKCU\...\Run`에 등록한다 |
| 작업 표시줄에 트레이 아이콘 고정 | — | Windows 11만. **다음 로그온부터** 적용된다 |
| 조회 주기 | 5분 | 2 · 5 · 10 · 30분. 2분 아래는 호출 한도에 걸린다 |
| 노란색으로 바뀌는 사용률 | 70% | 50~100, 5단위 |
| 빨간색으로 바뀌는 사용률 | 90% | 50~100, 5단위 |

노란은 빨간보다 5%p 아래에서 멈추고 반대도 같다. 서로 밀어내지 않는다.

설정은 `%APPDATA%\claude-usage-overlay\config.json`에 저장된다. 자동 실행과
아이콘 고정은 이 파일에 없다 — 진짜 상태가 레지스트리에 있고, 창을 열 때
거기서 읽는다.

**파일을 손으로 고치지 않는다.** 프로그램이 켜져 있는 동안 고치면 설정창이 닫힐 때
덮인다. 예전 판올림에 있던 트레이 메뉴의 "설정 파일 열기"는 사라졌다.

### 오버레이

| | 기본 (66×66) | 자세히 (190×62) |
|---|---|---|
| 마우스 올림 | 변화 없음 | 우상단에 ⚙·✕ |
| 왼쪽 클릭 | 사용량 ↔ 남은 시간 | 아무 일 없음 |
| 드래그 | 이동 | 이동 |
| 오른쪽 클릭 | 메뉴 | 메뉴 |

✕는 오버레이를 숨길 뿐 프로그램을 끄지 않는다. 트레이 메뉴로 되돌린다.

**창 위치와 사용량↔남은 시간 전환은 저장하지 않는다.** 다시 켜면 늘 화면 오른쪽
아래(작업 표시줄 위)에 사용량으로 뜬다.

갱신이 한 주기를 통째로 건너뛰면 숫자와 링 채움이 사라지고 흐린 `!`만 남는다.
낡은 숫자는 없느니만 못하기 때문이다.
```

`## 실행 파일 만들기` 절의 "약 19MB"를 "약 22MB"로 고친다 — 글꼴 5.4MB가
압축되어 3MB 안팎 늘어난다. Step 9에서 실제 크기를 확인하고 그 값으로 적는다.

`## 실행` 절의 "트레이 메뉴의 "시작할 때 자동 실행"을 켜면"은 그대로 둔다 —
그 항목은 남아 있다.

- [ ] **Step 7: 실제로 끝까지 돌려 확인**

```bash
python -m claude_usage_overlay
```

확인할 것:
- 기본 모드로 뜬다
- 트레이 메뉴가 `오버레이 숨기기 / 지금 갱신 / ─ / 설정… / 시작할 때 자동 실행 / ─ / 종료`
- 트레이의 `설정…`이 창을 연다 (**pystray 스레드에서 Tk를 건드리면 여기서 멈춘다**)
- 설정창에서 조회 주기를 2분으로 바꾸고 닫으면 `config.json`의 `poll_seconds`가 120
- 설정창에서 표시를 끄고 닫으면 오버레이가 사라지고, 트레이 메뉴가 `오버레이 보이기`
- 색 기준을 50/55로 바꾸고 닫으면 1초 안에 링 색이 바뀐다

첫 실행 경로는 `config.json`을 옮겨두고 확인한다.

```bash
mv "$APPDATA/claude-usage-overlay/config.json" "$APPDATA/claude-usage-overlay/config.json.bak" && python -m claude_usage_overlay
```

안내창이 한 번 뜨고, 끄고 다시 띄우면 **안 뜨는지** 본다. 확인이 끝나면 되돌린다.

```bash
mv "$APPDATA/claude-usage-overlay/config.json.bak" "$APPDATA/claude-usage-overlay/config.json"
```

- [ ] **Step 8: exe로 빌드해 글꼴이 실려 있는지 확인**

```bash
python build.py
```

`dist\ClaudeUsageOverlay.exe`를 실행해 **문구가 Pretendard로 그려지는지** 본다.
Segoe UI로 떨어졌으면 `--add-data`나 `bundle_dir()`이 잘못됐다. 크기를 확인해
README의 값을 그 숫자로 맞춘다.

```bash
python -c "from pathlib import Path; p=Path('dist/ClaudeUsageOverlay.exe'); print(f'{p.stat().st_size/1024/1024:.1f} MB')"
```

- [ ] **Step 9: 커밋**

```bash
git add claude_usage_overlay/tray.py claude_usage_overlay/__main__.py claude_usage_overlay/first_run.py README.md tests/test_tray.py tests/test_first_run.py
git commit -m "feat: 트레이 메뉴 개편과 설정창·첫 실행 배선, README 갱신"
```

---

## 마무리 확인

전부 끝난 뒤 한 번에 본다.

- [ ] `python -m pytest -q` — 실패 0
- [ ] `git status` — 남은 변경 없음
- [ ] 스펙 13장의 "범위에서 제외"가 지켜졌는지 — 오버레이 위치 저장 없음, 사용량↔남은
      시간 전환 상태 저장 없음, Windows 10 아이콘별 고정 없음, 탐색기 재시작 없음,
      7일 창 표시·알림·소리 없음
- [ ] Task 14 Step 6의 `IsPromoted` 확인 결과가 반영됐는지. **안 됐으면 문구 셋을
      고치는 것이 남아 있다** (`first_run.LAST_LINE_WIN11`,
      `settings_window.PROMOTE_HINT_WIN11`, `__main__`의 자동 시도)
