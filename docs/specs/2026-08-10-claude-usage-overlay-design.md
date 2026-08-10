# Claude Usage Overlay — 설계 문서

작성일: 2026-08-10

## 1. 목적

Claude 사용량을 확인하려면 Claude 앱의 설정창을 열어야 한다. 이 왕복을 없애고, 5시간 창 사용률을 항상 화면에 띄운다.

**이름 주의**: 기존 `claude-hud` 플러그인(터미널 statusline)과 별개의 프로젝트다. 패키지명은 `claude_usage_overlay`.

## 2. 왜 기존 도구로 안 되는가

`claude-hud` 플러그인은 Claude Code의 `statusLine` 설정으로 동작한다. 조사 결과 **Claude 데스크톱 앱의 Code 화면은 커스텀 statusLine을 렌더링하지 않는다.**

- 12초 동안 51회 프로세스를 샘플링했으나 `claude-hud` node 프로세스가 0회 관측됨 (`refreshInterval: 5` 설정 상태에서 2~3회는 떠야 함)
- 사용자 화면 확인 결과 입력창 아래에 HUD 없음

터미널 `claude` CLI에서는 정상 동작한다. 이 프로젝트는 앱 사용자를 위한 별도 표시기다.

## 3. 검증된 사실

모두 2026-08-10에 실측했다. 추정이 아니다.

### 3.1 사용량 조회

```
GET https://api.anthropic.com/api/oauth/usage
Authorization: Bearer <accessToken>
anthropic-beta: oauth-2025-04-20
```

응답 (1,823바이트, 왕복 330~570ms):

```json
{
  "five_hour": { "utilization": 23, "resets_at": "2026-08-10T05:40:00Z",
                 "limit_dollars": null, "used_dollars": null, "remaining_dollars": null },
  "seven_day": { "utilization": 15, "resets_at": "2026-08-12T17:00:00Z", ... },
  "seven_day_opus": null, "seven_day_sonnet": null,
  "extra_usage": { "is_enabled": false, ... }
}
```

- 이 계정에서 값이 채워지는 필드는 `five_hour`, `seven_day` 둘뿐이다. 모델별 항목은 모두 `null`이다.
- **쿼터를 소비하지 않는다.** 추론 호출이 아니다. 5회 연속 호출 동안 `utilization`이 23%에서 변하지 않음을 확인했다.

### 3.2 엔드포인트 자체의 호출 한도 (중요)

짧은 시간에 약 8회 호출하자 차단됐다.

```
429 rate_limit_error
retry-after: 287
```

**정확한 한도는 측정하지 않았다.** "8회쯤에서 걸리고 벌칙은 약 5분"만 안다. 이 미측정 상태를 전제로 보수적인 주기를 고른다.

### 3.3 토큰 갱신

```
POST https://console.anthropic.com/v1/oauth/token
Content-Type: application/json

{ "grant_type": "refresh_token",
  "refresh_token": "<refreshToken>",
  "client_id": "9d1c250a-e61b-44d9-88ed-5944d1962f5e" }
```

응답: `access_token`, `refresh_token`, `expires_in`, `refresh_token_expires_in`, `scope`, `token_uuid`, `organization`, `account`

| 항목 | 값 |
|---|---|
| accessToken 수명 | 28,800초 (8시간) |
| refreshToken 수명 | 2,585,692초 (약 30일) |
| **refreshToken 회전** | **매 갱신마다 새 값으로 교체됨** |

자격증명 파일: `%USERPROFILE%\.claude\.credentials.json`, 최상위 키 `claudeAiOauth`
필드: `accessToken`, `refreshToken`, `expiresAt`(ms), `refreshTokenExpiresAt`(ms), `scopes`, `subscriptionType`, `rateLimitTier`

## 4. 결정 사항

| 항목 | 결정 |
|---|---|
| 스택 | Python 3.12 + tkinter 8.6 + pystray + pillow |
| 오버레이 형태 | 링 게이지 + 텍스트 2줄 |
| 오버레이 내용 | 5시간 사용률 · 리셋 카운트다운 · 마지막 갱신 시각 |
| 창 속성 | 무테두리 · 반투명(alpha 0.82) · 항상 위 · 드래그 이동 |
| 경고 임계값 | 70% 주의(노랑) / 90% 위험(빨강) |
| 트레이 아이콘 | 숫자 + 아래에서 차오르는 배경, 수위 경계에서 숫자 색 반전 |
| 폴링 주기 | 300초 (5분) |
| 토큰 갱신 시점 | accessToken 만료 30분 전 |

7일 창은 오버레이에서 제외하고 트레이 툴팁에만 넣는다.

## 5. 모듈 구조

각 모듈은 하나의 책임만 갖고, 아래 모듈에만 의존한다.

### `credentials.py`

공개 인터페이스는 `get_access_token() -> str` 하나다. 호출자는 토큰이 유효하다는 사실만 알면 되고, 파일 위치도 갱신 시점도 모른다.

내부 동작: 파일 읽기 → 만료 30분 이내면 갱신 → 원자적 write-back.
갱신 불가 시 `ReloginRequired` 예외.

### `usage_client.py`

`fetch_usage(token) -> UsageSnapshot`. HTTP와 도메인의 경계다.

`UsageSnapshot(five_hour_pct: float, resets_at: datetime, seven_day_pct: float | None, fetched_at: datetime)`

예외: `RateLimited(retry_after: int)` / `Unauthorized` / `SchemaChanged`

### `poller.py`

백그라운드 스레드에서 300초마다 조회한다. 마지막 성공 스냅샷과 연속 실패 시간을 들고 있으면서 상태를 **하나의 값**으로 계산한다. UI는 이 상태만 보면 된다.

```
Status = OK | STALE | RATE_LIMITED | RELOGIN | SCHEMA_ERROR
```

### `overlay.py`

tkinter 창. Canvas 호(arc)로 링을 그린다.

**1초마다 틱을 돌지만 네트워크는 건드리지 않는다.** 카운트다운은 `resets_at`에서 로컬 계산한다. 화면은 매초 살아 움직이고 API는 5분에 한 번만 부른다.

### `tray.py`

pystray 아이콘. pillow로 16×16 이미지를 그린다.

### `config.py`

`%APPDATA%\claude-usage-overlay\config.json` — 창 위치, 임계값, 폴링 주기.

## 6. 데이터 흐름

```
[poller 스레드]  만료 30분 전 갱신 ──→ credentials ──→ .credentials.json
       │ 300초마다 조회
       ↓
  UsageSnapshot + Status ──(queue)──→ [메인 스레드] overlay + tray
```

tkinter는 메인 스레드에서만 건드린다. poller는 큐로만 전달한다. 이 경계를 지키면 네트워크 대기 중에 UI가 멈추지 않는다.

## 7. 상태별 표시

| 상태 | 오버레이 | 트레이 아이콘 |
|---|---|---|
| 정상 (~69%) | 초록 링 + 숫자 | 초록 채움 + 숫자 |
| 주의 (70~89%) | 노랑 링 | 노랑 채움 + 숫자 |
| 위험 (90~99%) | 빨강 링 | 빨강 채움 + 숫자 |
| 한도 소진 (100%) | 빨강 꽉 참 | 빨강 꽉 참 + **✕** |
| 갱신 실패 | 링 흐림 + "N분째 갱신 실패" | 아이콘 흐림 |
| 재로그인 필요 | 링 비움 + "재로그인 필요 / claude auth login" | 회색 + **!** |

네 가지 특수 상태는 배경색만으로 구분된다 — 초록 계열 / 빨강 / 회색 / 흐림. 기호를 읽기 전에 색이 먼저 말한다.

**100%는 숫자를 넣지 않는다.** 16px 폭에 세 자리 굵은 숫자는 물리적으로 들어가지 않는다. ✕로 대체한다.

## 8. 실패 처리

| 상황 | 동작 |
|---|---|
| 네트워크 실패 | 마지막 값 유지, 흐리게, "N분째 갱신 실패" |
| 429 | `retry-after` 헤더를 그대로 존중하고 그때까지 호출하지 않음 |
| 401 | 파일 재읽기 → 갱신 시도 → 실패 시 `RELOGIN` |
| refreshToken 만료 | `RELOGIN` 상태 고정, 안내 문구 표시 |
| 스키마 변경 | "데이터 형식이 바뀜" 표시. **숫자를 지어내지 않는다** |

폴링 실패 시 지수 백오프(300 → 600 → 1200초, 최대 1800초).

## 9. 가장 위험한 부분 — 토큰 회전

갱신할 때마다 refreshToken이 새 값으로 회전한다. 응답의 새 refreshToken을 저장하지 못하면 이전 것은 이미 죽어 있어 재로그인해야 한다. 이 프로젝트에서 가장 깨지기 쉬운 지점이다.

세 가지로 방어한다.

1. **원자적 쓰기** — 임시 파일에 쓰고 `os.replace`. 쓰는 도중 죽어도 파일이 반쯤 망가지지 않는다.
2. **갱신 직전 재읽기** — 사용자가 가끔 터미널 CLI를 쓰면 Claude Code도 같은 파일을 회전시킨다. 갱신 전에 파일을 다시 읽어 이미 갱신됐는지 확인하고, 그렇다면 우리는 갱신하지 않는다. 401을 받았을 때도 우리 토큰을 버리기 전에 파일부터 다시 읽는다.
3. **꼭 필요할 때만 갱신** — 만료 30분 전에만. 회전 횟수를 줄이는 것이 사고 확률을 줄인다.

`refreshTokenExpiresAt`도 응답의 `refresh_token_expires_in`으로 함께 갱신한다.

**도구가 30일 넘게 꺼져 있으면 재로그인이 필요하다.** 이건 피할 수 없다. 조용히 실패하는 대신 명확히 표시한다 — 이번 조사에서 인증이 죽어 있던 것을 우연히 발견한 것과 같은 상황을 만들지 않는다.

## 10. 테스트

HTTP를 목으로 두고 단위 테스트한다. 아래 셋이 로직의 전부다.

- `credentials` — 만료 판정, 회전 처리, 원자적 쓰기, 외부 갱신 감지
- `usage_client` — 정상 파싱, 필드 누락, 429(retry-after 추출), 401
- `poller` — 백오프 계산, 상태 전이

UI는 수동 확인한다.

## 11. 범위에서 제외

7일 창 상시 표시(툴팁에만) · 모델별 사용량(계정에 `null`) · 히스토리 그래프 · 알림 팝업 · 다중 계정 · macOS/Linux 지원.

## 12. 미해결 사항

- **엔드포인트 호출 한도의 정확한 값** — 5분 주기는 안전하다고 판단해 고른 값이지 측정값이 아니다. 구현 후 장시간 돌려 429가 나오는지 확인한다.
- **`client_id`의 안정성** — 공개된 Claude Code OAuth client id를 사용한다. 변경되면 갱신이 깨진다. 401/400 응답 시 진단 가능한 로그를 남긴다.
- **엔드포인트의 비공개성** — `/api/oauth/usage`는 문서화된 공개 API가 아니다. 예고 없이 바뀔 수 있다. 그래서 `SchemaChanged`를 별도 상태로 두고, 형식이 바뀌면 잘못된 숫자를 보여주는 대신 바뀌었다고 말한다.
