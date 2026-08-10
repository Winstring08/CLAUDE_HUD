# Claude Usage Overlay

Claude 사용량(5시간 창)을 Windows 화면에 항상 띄우는 상주 프로그램.

## 필요 조건

- Windows, Python 3.12
- 터미널에서 `claude auth login`이 완료된 상태

## 설치

```bash
pip install pystray pillow
```

## 실행

```bash
python -m claude_usage_overlay
```

트레이 메뉴의 "시작할 때 자동 실행"을 켜면 로그인 시 자동으로 뜬다.

## 설정

`%APPDATA%\claude-usage-overlay\config.json` — 트레이 메뉴의 "설정 파일 열기"로도 열 수 있다.

| 키 | 기본값 | 설명 |
|---|---|---|
| `poll_seconds` | 300 | 조회 주기(초). 최소 120 |
| `warn_pct` | 70 | 노란색으로 바뀌는 사용률 |
| `danger_pct` | 90 | 빨간색으로 바뀌는 사용률 |
| `x`, `y` | 없음 | 오버레이 위치. 드래그하면 자동 저장 |
| `overlay_visible` | `true` | 오버레이 표시 여부. 트레이 메뉴로 바뀐다 |

`poll_seconds`·`warn_pct`·`danger_pct`를 손으로 고치면 **다음 실행부터** 적용된다. 프로그램은
저장할 때 `x`·`y`·`overlay_visible`만 덮어쓰므로 고쳐둔 값이 사라지지는 않는다.

## 주의

**이 프로그램은 자격증명 파일을 읽기만 한다.** 토큰을 갱신하지 않고 파일에 쓰지도
않는다. refreshToken은 갱신할 때마다 회전하므로, 이 프로그램이 회전시키면 옛 토큰을
들고 있는 Claude Code와 데스크톱 앱의 인증이 깨진다.

대가는 하나다 — **Claude Code를 8시간 넘게 쓰지 않으면 토큰이 만료되어 조회가 멈춘다.**
그때는 "토큰 만료 — Claude Code를 한 번 실행하세요"가 뜬다. 한 번 실행하면 낫는다.

30일 넘게 이 프로그램과 Claude Code를 모두 쓰지 않으면 refreshToken까지 만료되어
`claude auth login`을 다시 해야 한다.

사용량 엔드포인트는 문서화된 공개 API가 아니다. 예고 없이 바뀔 수 있고, 그때는
숫자를 지어내는 대신 "데이터 형식이 바뀜"을 표시한다.

## 테스트

```bash
pip install pytest
python -m pytest -v
```
