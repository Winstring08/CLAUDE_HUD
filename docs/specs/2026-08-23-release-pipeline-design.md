# 배포 파이프라인 — 설계 문서

작성 2026-08-23. 기준 커밋 `af620b4`.

지금까지 exe는 개발 PC에서 `python build.py`로만 났고, 그 파일을 남에게 줄 경로가
없었다. 이 문서는 **태그 하나로 GitHub Releases에 exe가 올라가게 하는 것**까지만
다룬다. 프로그램의 동작을 바꾸는 부분은 버전 표시 한 줄뿐이다.

## 1. 목적

`v0.1.0` 태그를 밀면 GitHub Actions가 Windows에서 빌드해 **초안(draft) 릴리스**에
exe와 해시를 붙인다. 노트를 다듬고 게시 버튼을 누르면 공개된다. 받는 사람은
파일 하나를 내려받아 실행한다 — 파이썬도 의존성도 필요 없다.

다섯 덩어리다.

1. **버전의 단일 출처** — 태그·소스·실행 중인 exe가 같은 숫자를 말하게 한다
2. **릴리스 워크플로** — 태그 푸시 → 테스트 → 빌드 → 초안 릴리스
3. **테스트 워크플로** — push·PR에서 pytest만 돈다
4. **exe 파일 속성** — 탐색기 속성 창에 제품 이름·버전·저작권이 보이게 한다
5. **라이선스와 문서** — MIT, 그리고 README에 "받기" 절

## 2. 되돌릴 수 없는 결정

이 작업에서 **틀렸을 때 코드 수정으로 원상복구되지 않는** 것은 셋뿐이다. 나머지는
전부 나중에 고쳐도 비용이 같다.

| 결정 | 값 | 나중에 바꾸면 누구 것이 깨지는가 |
|---|---|---|
| exe 파일 이름 | `ClaudeUsageOverlay.exe` | 받은 사람의 바로가기와 자동 실행 레지스트리 값이 옛 경로를 가리킨다. 프로그램이 뜨지 않고, 본인이 손으로 고쳐야 한다 |
| 버전 체계 | `v0.1.0` (SemVer, `v` 접두) | 한 번 나간 태그는 회수되지 않는다. 되돌리려면 상위 번호를 새로 내는 수밖에 없다 |
| 라이선스 | MIT, 저작권자 **권승현** | 이미 나간 판은 영원히 MIT다. 나중에 조여도 그 시점 이후 코드에만 걸린다 |

exe 이름은 지금 `build.py`가 내는 이름과 같다. 이미 이 이름으로 자동 실행을
등록해 쓰던 사람이 있으므로 바꾸지 않는다.

## 3. 실측으로 확인한 것

이 PC(Windows 11 26200, Python 3.12.10)에서 쟀다.

### 3.1 테스트는 전부 통과한다

```
python -m pytest -q
362 passed in 3.07s
```

네트워크는 `monkeypatch`로 막혀 있고(`tests/test_http_client.py`,
`tests/test_usage_client.py`), 레지스트리에 실제로 쓰는 테스트는 없다
(`grep -n "winreg\." tests/*.py` → 결과 없음). 그러므로 CI 러너의 네트워크나
레지스트리 상태에 좌우되지 않는다.

### 3.2 지금 깔려 있는 판

```
python -m pip list | grep -iE "pystray|pillow|pyinstaller|pytest"
pillow                    12.3.0
pyinstaller               6.22.0
pystray                   0.19.5
pytest                    9.1.1
```

362개가 통과한 것은 **이 조합**이다. CI가 고정할 값도 이것이다.

### 3.3 태그는 하나도 없다

```
git tag -l              → 결과 없음
git ls-remote --tags origin → 결과 없음
```

`v0.1.0`이 비어 있다. `pyproject.toml`도 이미 `0.1.0`이므로 첫 릴리스에 번호를
올릴 필요가 없다.

### 3.4 저장소는 public이고 라이선스가 없다

```
gh repo view Winstring08/CLAUDE_HUD --json visibility,licenseInfo
{"licenseInfo":null,"visibility":"PUBLIC"}
```

라이선스 없는 public 저장소는 법적으로 "저작권 전부 보유"다. 받는 사람이 실행은
해도 포크·재배포할 권리가 없다. 배포를 시작하기 전에 정해야 한다.

### 3.5 pystray는 비활성 메뉴 항목을 지원한다

```
python -c "import inspect, pystray; print(inspect.signature(pystray.MenuItem.__init__))"
(self, text, action, checked=None, radio=False, default=False, visible=True, enabled=True)
```

`enabled=False`가 있다. 버전 표시를 누를 수 없는 항목으로 넣을 수 있다.

### 3.6 `dynamic = ["version"]`은 이 레이아웃에서 동작한다

이 프로젝트의 최상위 구조(`claude_usage_overlay`·`tests`·`docs`·`build`·`dist`·
`app.py`)를 그대로 복제해 놓고 setuptools에 메타데이터를 만들게 했다.

```
`flat-layout` detected -- analysing .
discovered packages -- ['claude_usage_overlay', 'claude_usage_overlay.fonts']
Name: claude-usage-overlay
Version: 0.1.0
```

setuptools가 `tests`·`docs`·`build`·`dist`를 기본 제외 목록으로 걸러내고
`claude_usage_overlay`만 잡는다. `version.py`의 값이 그대로 올라온다.

**단, `[build-system]`을 새로 넣어야 한다** (`setuptools>=64`,
`setuptools.build_meta`). 없으면 `[tool.setuptools.dynamic]`을 아무도 읽지 않는다.

### 3.7 UPX는 이 PC에 없다 — 그래서 CI와 달라질 수 있다

```
which upx  → 없음
ls -la dist/ClaudeUsageOverlay.exe → 21,838,150 바이트
```

**PyInstaller는 UPX가 PATH에 있으면 묻지 않고 쓴다.** 지금 21.8MB exe는 UPX가
없어서 압축이 안 된 것이지, 안 쓰기로 정해서가 아니다. CI 러너에 UPX가 있으면
개발 PC와 다른 exe가 나고, **UPX로 압축된 바이너리는 백신 오탐을 훨씬 많이
받는다.** 서명이 없는 이 exe에는 특히 나쁘다.

이건 개발 PC에서 아무리 돌려도 드러나지 않는 축이다. **`build.py`에 `--noupx`를
명시해** 어느 기계에서 빌드하든 같은 결과가 나오게 한다. 러너에 UPX가 있는지를
확인할 필요조차 없어진다.

### 3.8 `ClaudeUsageOverlay.spec`은 추적되지 않는다

```
git ls-files ClaudeUsageOverlay.spec       → 결과 없음
git check-ignore -v ClaudeUsageOverlay.spec → .gitignore:11:*.spec
```

작업 폴더에 있지만 `.gitignore`에 걸린 로컬 빌드 부산물이다. `build.py`가 매번
덮어쓴다. 개인 절대경로가 공개되는 문제는 없고, 치울 것도 없다.

## 4. 버전의 단일 출처

지금 버전은 `pyproject.toml`에 `0.1.0` 한 군데뿐이고 **실행 중인 프로그램은 자기
버전을 모른다**. 배포를 시작하면 버그 제보를 받을 때 "몇 판을 쓰십니까"를 물을
수단이 없다.

**`claude_usage_overlay/version.py`에 `__version__ = "0.1.0"` 한 줄을 두고 그것을
유일한 원본으로 삼는다.**

- `pyproject.toml`은 `dynamic = ["version"]` + `[tool.setuptools.dynamic]`으로 그 값을
  끌어온다. 손으로 맞추는 자리가 하나로 줄어든다. `[build-system]`을 함께 넣는다
  (§3.6에서 실제로 돌려 확인했다)
- 트레이 메뉴 맨 위에 `pystray.MenuItem(f"버전 {__version__}", None, enabled=False)`와
  구분선을 넣는다
- CI가 태그와 대조해 다르면 **빌드 전에** 실패시킨다 (§5.3)

`importlib.metadata`로 읽지 않는다. 이 앱은 `pip install`된 적이 없고 exe 안에도
패키지 메타데이터가 없어서, 그 방식은 소스 실행과 exe에서 서로 다르게 동작한다.
파일에 박힌 문자열은 두 경우 모두 같은 값을 낸다.

`tests/test_tray.py`가 `tray.py`의 본문 문자열을 훑는 테스트를 가지고 있으므로
(그 파일 주석에 그렇게 적혀 있다) 메뉴 항목을 늘리면 그 테스트를 함께 본다.

## 5. 릴리스 워크플로

`.github/workflows/release.yml` 하나. `v*` 태그 푸시에 걸리고 `windows-latest`에서
돈다. `permissions: contents: write`가 필요하다.

### 5.1 순서가 곧 안전장치다

```
체크아웃 → Python 3.12 → 의존성 설치 → 버전 대조 → pytest → build.py
        → SHA-256 → 초안 릴리스 생성 + 첨부
```

앞 단계가 깨지면 릴리스는 **만들어지지 않는다.** 초안으로 만드는 이유도 같다 —
빌드가 통과해도 사람이 노트를 보고 게시할 때까지는 아무에게도 알림이 가지 않는다.

### 5.2 의존성을 고정한다

`requirements-build.txt`에 §3.2의 판을 그대로 박는다.

```
pystray==0.19.5
pillow==12.3.0
pyinstaller==6.22.0
pytest==9.1.1
```

고정하지 않으면 어제 성공한 빌드가 오늘 깨지고, 그 사실이 **태그를 민 다음에**
드러난다. 올릴 때는 손으로 올리고 커밋에 남긴다.

### 5.3 버전 대조

태그 `v0.1.0`에서 `v`를 뗀 `0.1.0`이 `claude_usage_overlay.version.__version__`과
같은지 본다. 다르면 그 자리에서 실패한다.

이 검사가 없으면 "0.2.0 릴리스에 자기를 0.1.0이라 말하는 exe"가 나가고, 그건
받은 사람 쪽에서만 드러난다.

### 5.4 릴리스 생성은 `gh` CLI로 한다

`gh release create "$TAG" --draft --title ... ClaudeUsageOverlay.exe SHA256SUMS.txt`

`gh`는 windows 러너에 이미 깔려 있다. 서드파티 액션을 쓰지 않는 이유는 그것이
태그가 조용히 옮겨질 수 있는 공급망 표면이기 때문이다. 여기서 아끼는 코드는
몇 줄뿐이라 바꿀 값어치가 없다.

### 5.5 첨부물은 둘이다

| 파일 | 왜 |
|---|---|
| `ClaudeUsageOverlay.exe` | 받는 사람이 실제로 쓰는 것 |
| `SHA256SUMS.txt` | 코드 서명이 없으므로 **해시가 유일한 대조 수단**이다 |

### 5.6 릴리스 노트

자동 생성에 맡기지 않는다. 커밋 제목이 한국어 관용문이라 자동 생성 목록은 읽는
사람에게 뜻이 서지 않는다. 초안 상태에서 손으로 쓴다.

## 6. 테스트 워크플로

`.github/workflows/ci.yml`. **`main`에 대한 push와 `main`을 향한 pull_request**에서
`windows-latest`로 pytest만 돌린다. 모든 브랜치에 걸지 않는다 — 작업 중인 브랜치를
밀 때마다 도는 것은 이 프로젝트 규모에 과하다.

릴리스 워크플로 안에서도 테스트는 돌지만, 그것만 있으면 **테스트가 깨진 사실을
태그를 밀고 나서야 알게 된다.** 그리고 이 워크플로가 §9의 미확인 항목(Tk가 CI에서
뜨는가)을 태그 없이 먼저 확인해 주는 수단이기도 하다.

## 7. `build.py`에서 바뀌는 것

둘이다.

### 7.1 `--noupx`를 명시한다

§3.7의 이유다. 빌드하는 기계에 UPX가 깔려 있는지가 결과를 바꾸지 않게 못 박는다.

### 7.2 exe 파일 속성

`build.py`가 아이콘을 생성하듯 **VS_VERSION_INFO 파일도 생성해** PyInstaller에
`--version-file`로 넘긴다. 탐색기 → 속성 → 자세히에 다음이 보인다.

| 항목 | 값 |
|---|---|
| ProductName | Claude Usage Overlay |
| FileDescription | Claude 사용량 오버레이 |
| FileVersion / ProductVersion | `__version__`에서 (0, 1, 0, 0) |
| CompanyName | 권승현 |
| LegalCopyright | Copyright (c) 2026 권승현. MIT License. |
| OriginalFilename | ClaudeUsageOverlay.exe |

서명이 없는 exe는 메타데이터까지 비어 있으면 백신 오탐을 더 받는다. 그리고
사용자가 버전을 확인할 두 번째 경로가 생긴다 — 프로그램을 띄우지 않고도 본다.

## 8. 라이선스와 문서

### 8.1 LICENSE

MIT 전문, 저작권자 `2026 권승현`. **파일 이름이 정확히 `LICENSE`여야** GitHub이
저장소 우상단에 배지를 붙인다.

### 8.2 README에 "받기" 절

지금 README는 첫 절부터 `pip install`인데, 이제 방문자 대부분은 소스를 볼 사람이
아니라 exe를 받을 사람이다. "필요 조건" 다음에 "받기"를 넣고 기존 "설치"·"실행"은
그 아래로 내린다.

들어갈 것:

- Releases 링크와 "`ClaudeUsageOverlay.exe` 하나만 받으면 된다"
- **SmartScreen 경고 넘는 법** — "추가 정보 → 실행". 왜 뜨는지(코드 서명 인증서가
  없음)도 한 줄. 이걸 안 적으면 처음 받은 사람 상당수가 거기서 멈춘다
- 해시 대조: `certutil -hashfile ClaudeUsageOverlay.exe SHA256`
- 전제조건 — Windows, 그리고 **`claude auth login`이 끝나 있어야 한다.** 안 돼 있으면
  프로그램이 아무 숫자도 못 보여준다

기존 "실행 파일 만들기" 절은 남기되 **소스에서 직접 빌드하려는 사람용**으로
성격을 바꾼다.

### 8.3 Pretendard는 이미 조건을 지키고 있다

OFL 1.1은 재배포 시 라이선스 동봉을 요구하는데 `fonts/OFL.txt`가 exe에 함께
묶인다(`build.py`의 `--add-data`). 폰트 이름을 바꾸지 않았고 따로 팔지도 않는다.
README에 이미 명시돼 있어 손댈 곳이 없다.

## 9. 확인되지 않은 것

구현 세션에서 **실제로 돌려서** 확인한다. 읽어서 판정하지 않는다.

1. **`windows-latest`에서 Tk 루트가 만들어지는가.** `tests/conftest.py`가 진짜
   `tk.Tk()`를 만든다. 안 되면 362개 중 Tk를 쓰는 것들이 통째로 ERROR가 된다.
   §6의 ci.yml을 먼저 올려 태그 없이 확인한다. 만약 안 되면 그때 대안(가상
   디스플레이 또는 Tk 테스트 분리)을 정한다 — 이 문서는 그 대안을 미리 고르지 않는다
2. **`--version-file`의 한글이 exe 리소스까지 살아서 가는가.** CompanyName이
   `권승현`이다. **파일 단계까지는 확인했다** — PyInstaller의 `VSVersionInfo`로
   `권승현`·`Claude 사용량 오버레이`를 UTF-8로 쓰고
   `load_version_info_from_text_file()`로 다시 읽어 같은 문자열을 얻었다.
   남은 것은 **빌드된 exe 안**이다. `read_version_info_from_executable()`과 탐색기
   속성 창으로 확인한다. 깨지면 로마자로 적는다
3. **CI에서 난 exe가 실제로 뜨는가.** 빌드가 exit 0이라고 실행되는 것은 아니다.
   첫 릴리스 초안의 exe를 내려받아 한 번 띄워 본다. 이걸 안 하면 "빌드는 됐는데
   실행하면 죽는 exe"를 게시하게 된다

## 10. 범위 밖

의도적으로 넣지 않는다.

- **자동 업데이트·업데이트 알림.** 받은 사람은 새 판이 난 것을 모른다. 릴리스를
  몇 번 돌려보고 필요해지면 그때 더한다
- **코드 서명.** 인증서 비용과 보관(HSM)이 지금 단계에 무겁다. SmartScreen 경고는
  문서로 안내한다
- **설치 프로그램(Inno Setup/MSI), winget 등록.** exe 하나로 시작한다
- **CHANGELOG.md.** 릴리스 노트가 그 역할을 한다
- **macOS·Linux 빌드.** 이 프로그램은 레지스트리와 Windows 트레이에 매여 있다

## 11. 실패 처리

| 무엇이 깨지면 | 어떻게 되나 |
|---|---|
| 버전 대조 실패 | 워크플로가 그 자리에서 멈춘다. 릴리스 없음. 태그를 지우고 `version.py`를 고쳐 다시 민다 |
| pytest 실패 | 빌드에 들어가지 않는다. 릴리스 없음 |
| PyInstaller 실패 | 릴리스 없음. 로그가 Actions에 남는다 |
| `gh release create` 실패 | exe는 났지만 릴리스가 없다. 워크플로를 다시 돌리거나 Actions 아티팩트에서 꺼낸다 |
| 게시 후 exe가 안 뜬다 | 릴리스를 초안으로 되돌리거나 삭제하고, 고쳐서 상위 번호로 다시 낸다. **태그는 재사용하지 않는다** |
