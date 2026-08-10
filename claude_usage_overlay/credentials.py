"""자격증명 파일 읽기와 토큰 갱신.

**처음에는 읽기만 했다.** refreshToken은 갱신할 때마다 회전하므로, 우리가
회전시키면 옛 토큰을 들고 있는 다른 클라이언트의 인증이 깨질 수 있다. 그래서
갱신은 Claude Code에 맡기고 우리는 편승하기로 했다(스펙 9장).

**그 전제가 실측으로 무너졌다.** accessToken이 만료된 뒤에도 데스크톱 앱은
멀쩡히 동작하는데 `.credentials.json`은 8시간 전 그대로였다 — 만료 3분 뒤
대화가 오가는 동안 90초를 지켜봐도 mtime이 움직이지 않았다. 앱은 자체
저장소를 쓰고 이 파일을 갱신하지 않는다.

편승할 대상이 없으므로 우리가 갱신한다. 이 프로그램은 데스크톱 앱 사용자를
위해 만든 것인데, 토큰을 살리자고 터미널 `claude`를 켜라고 하면 존재 이유와
어긋난다.

**대신 스펙 9장이 정한 방어 셋을 지킨다.**

  1. 원자적 쓰기 — 임시 파일에 쓰고 `os.replace`. 반쯤 쓰인 파일이 남지 않는다
  2. 갱신 직전 재읽기 — 그 사이 누가 갱신했으면 우리는 회전시키지 않는다
  3. 만료 30분 전에만 — 회전 횟수를 줄이는 것이 사고 확률을 줄인다

여기에 하나 더한다. **갱신에 실패해도 살아 있는 토큰은 버리지 않는다.**
네트워크가 잠깐 끊긴 것과 인증이 죽은 것은 다르다.
"""

import json
import os
import time
from pathlib import Path
from typing import Callable

from . import http_client
from .models import ReloginRequired

CREDENTIALS_PATH = Path(os.environ.get("USERPROFILE", str(Path.home()))) / ".claude" / ".credentials.json"
OAUTH_KEY = "claudeAiOauth"

TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
# Claude Code에 내장된 공개 OAuth client id. 계정을 식별하지 않는다 —
# 공개 클라이언트는 비밀값을 숨길 수 없으므로 처음부터 공개 전제로 설계된다.
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"

# **User-Agent를 반드시 보낸다.** 이 엔드포인트는 Cloudflare 뒤에 있고,
# urllib의 기본값(`Python-urllib/3.12`)으로 보내면 요청이 OAuth 서버에
# 닿지도 못한 채 차단된다 — 실측으로 `403` + `error code: 1010`(text/plain)이
# 돌아온다. 아무 이름이나 붙이면 통과한다.
USER_AGENT = "claude-usage-overlay/0.1"

# OAuth 서버가 "이 refreshToken은 못 쓴다"고 말하는 코드들. 다시 시도해도
# 결과가 같으므로 사용자에게 재로그인을 요구한다.
#
# **이 목록에 없는 실패는 재로그인 사유가 아니다.** Cloudflare 차단(1010),
# 호출 한도(429), 서버 오류(5xx)는 전부 기다리면 낫는 것들인데, 상태 코드만
# 보고 뭉뚱그리면 멀쩡한 인증을 두고 재로그인하라고 말하게 된다.
FATAL_OAUTH_ERRORS = frozenset(
    {"invalid_grant", "invalid_client", "unauthorized_client", "invalid_request"}
)

# 만료 30분 전부터 갱신한다. 더 일찍 갱신하면 회전이 잦아지고, 더 늦추면
# 폴링 한 번을 만료된 토큰으로 날린다.
REFRESH_MARGIN_MS = 30 * 60 * 1000

# 화면에 그대로 나가는 문구다. 짧게 유지한다 — 오버레이 창 폭이 가장 긴
# 문구에서 역산되므로, 여기가 길면 평소 화면에 빈 공간만 늘어난다.
RELOGIN_MSG = "재로그인 필요 — claude auth login"
STALE_TOKEN_MSG = "토큰 만료 — 갱신 실패"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _is_fatal_oauth_error(body: bytes) -> bool:
    """이 응답이 "refreshToken을 못 쓴다"는 뜻인지.

    상태 코드로 판단하면 안 된다. 이 엔드포인트 앞에는 Cloudflare가 있어서,
    막히면 OAuth 서버와 무관한 `403` + `error code: 1010`(text/plain)이 온다.
    그걸 토큰 거부로 읽으면 멀쩡한 인증을 두고 재로그인하라고 말하게 된다.

    진짜 거부는 JSON으로 오고 `error`에 사유가 담긴다. 두 형태를 다 본다 —
    OAuth 규격의 `{"error": "invalid_grant"}`와 Anthropic 쪽의
    `{"error": {"type": "..."}}` 둘 다 쓰인다(실측).
    """
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, TypeError, ValueError):
        return False   # JSON이 아니면 OAuth 서버가 준 답이 아니다
    if not isinstance(data, dict):
        return False

    error = data.get("error")
    if isinstance(error, dict):
        error = error.get("type")
    return isinstance(error, str) and error in FATAL_OAUTH_ERRORS


class CredentialStore:
    def __init__(
        self,
        path: Path | None = None,
        now_ms: Callable[[], int] = _now_ms,
        request_fn: Callable = http_client.request,
    ) -> None:
        self._path = path or CREDENTIALS_PATH
        self._now_ms = now_ms
        self._request = request_fn

    # --- 공개 인터페이스 -------------------------------------------------

    def get_access_token(self) -> str:
        """쓸 수 있는 accessToken. 만료가 가까우면 갱신해서 돌려준다.

        호출할 때마다 파일을 다시 읽는다. 캐시하면 다른 프로세스가 갱신한
        새 토큰을 놓친다.
        """
        creds = self._read()
        now = self._now_ms()

        refresh_expires_at = self._expiry_ms(creds.get("refreshTokenExpiresAt"))
        if refresh_expires_at is not None and refresh_expires_at <= now:
            # 여기서 갱신은 무의미하다. 사용자가 다시 로그인해야 한다.
            raise ReloginRequired(RELOGIN_MSG)

        expires_at = self._expiry_ms(creds.get("expiresAt"))
        if expires_at is not None and expires_at - now > REFRESH_MARGIN_MS:
            return creds["accessToken"]

        return self._refresh(now)

    # --- 갱신 ------------------------------------------------------------

    def _refresh(self, now: int) -> str:
        """토큰을 새로 받아 파일에 쓰고 새 accessToken을 돌려준다."""
        # 방어 2: 그 사이 누가 갱신했을 수 있다. 다시 읽어 확인한다.
        # 이미 갱신돼 있으면 refreshToken을 한 번 덜 회전시킨다.
        creds = self._read()
        expires_at = self._expiry_ms(creds.get("expiresAt"))
        if expires_at is not None and expires_at - now > REFRESH_MARGIN_MS:
            return creds["accessToken"]

        refresh_token = creds.get("refreshToken")
        if not refresh_token:
            raise ReloginRequired(RELOGIN_MSG)

        try:
            # **요청을 보내기 전에** 저장할 수 있는지 확인한다.
            #
            # 서버는 새 토큰을 내주는 순간 옛 refreshToken을 무효화한다. 그때
            # 우리가 저장에 실패하면 새 값도 옛 값도 없어져 사용자가 재로그인해야
            # 한다 — 이 프로그램이 사용자에게 입힐 수 있는 유일한 되돌릴 수 없는
            # 피해다. 저장 실패의 대부분(권한·디스크 부족)은 미리 알 수 있으므로,
            # 회전을 시작하기 전에 걸러낸다. 여기서 실패하면 아직 아무 일도
            # 일어나지 않았으므로 다음 폴링에 그대로 다시 시도하면 된다.
            self._check_writable()
            issued = self._request_tokens(refresh_token)
        except ReloginRequired:
            raise
        except Exception as err:
            # 네트워크가 잠깐 끊긴 것과 인증이 죽은 것은 다르다.
            # 지금 토큰이 아직 살아 있으면 그걸로 버틴다 — 30분 여유가 그 몫이다.
            if expires_at is not None and expires_at > now:
                return creds["accessToken"]
            raise ReloginRequired(STALE_TOKEN_MSG) from err

        self._save(issued, now)
        return issued["access_token"]

    def _check_writable(self) -> None:
        """실제로 파일을 쓸 수 있는지 미리 시험한다. 못 쓰면 OSError.

        진짜 파일은 건드리지 않는다. 같은 폴더에 탐침 파일을 만들었다 지운다 —
        같은 폴더여야 권한과 디스크 여유를 제대로 본다.
        """
        probe = self._path.with_suffix(".json.probe")
        try:
            probe.write_text("{}", encoding="utf-8")
        finally:
            try:
                probe.unlink(missing_ok=True)
            except OSError:
                pass

    def _request_tokens(self, refresh_token: str) -> dict:
        res = self._request(
            "POST",
            TOKEN_URL,
            {"Content-Type": "application/json", "User-Agent": USER_AGENT},
            json_body={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": CLIENT_ID,
            },
            timeout=20.0,
        )

        if res.status != 200:
            if _is_fatal_oauth_error(res.body):
                raise ReloginRequired(RELOGIN_MSG)
            # 여기까지 온 것은 기다리면 나을 수 있는 실패다.
            raise OSError(f"토큰 갱신 실패 (HTTP {res.status})")

        data = json.loads(res.body)
        if not data.get("access_token") or not data.get("refresh_token"):
            raise OSError("갱신 응답에 토큰이 없습니다")
        return data

    def _save(self, issued: dict, now: int) -> None:
        """새 토큰을 파일에 쓴다. **우리가 모르는 필드는 건드리지 않는다.**

        방어 1: 임시 파일에 쓰고 os.replace로 바꿔치운다. 쓰는 도중에 죽어도
        원본은 온전하고, 반쯤 쓰인 파일을 다른 프로세스가 읽는 일도 없다.

        최상위 구조와 claudeAiOauth 안의 다른 키(scopes·subscriptionType·
        rateLimitTier 등)를 그대로 둔다. 우리가 아는 필드만 덮어쓴다.
        """
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raw = {}
        except (OSError, json.JSONDecodeError):
            raw = {}

        creds = dict(raw.get(OAUTH_KEY) or {})
        creds["accessToken"] = issued["access_token"]
        creds["refreshToken"] = issued["refresh_token"]

        expires_in = issued.get("expires_in")
        if isinstance(expires_in, (int, float)):
            creds["expiresAt"] = now + int(expires_in * 1000)

        refresh_expires_in = issued.get("refresh_token_expires_in")
        if isinstance(refresh_expires_in, (int, float)):
            creds["refreshTokenExpiresAt"] = now + int(refresh_expires_in * 1000)

        scope = issued.get("scope")
        if isinstance(scope, str) and scope:
            creds["scopes"] = scope.split()

        raw[OAUTH_KEY] = creds

        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)

    # --- 내부 ------------------------------------------------------------

    @staticmethod
    def _expiry_ms(value) -> int | None:
        """만료 시각을 ms 정수로. 필드가 없으면 None.

        숫자로 안 읽히면 파일이 우리가 아는 형식이 아니라는 뜻이므로
        ReloginRequired로 바꾼다. 여기서 ValueError를 흘리면 폴러의
        except Exception이 받아 "N분째 갱신 실패"를 띄우고, 사용자는
        인터넷을 의심하며 진짜 원인을 못 본다. _read가 막는 구멍과 같다.
        """
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError) as err:
            raise ReloginRequired(RELOGIN_MSG) from err

    def _read(self) -> dict:
        # AttributeError까지 잡는 이유: claudeAiOauth 값이 객체가 아니면
        # (`{"claudeAiOauth": "..."}`) .get에서 AttributeError가 난다. 이걸
        # 흘리면 폴러의 except Exception이 받아 "N분째 갱신 실패"를 띄운다 —
        # 파일이 손상됐는데 네트워크 문제처럼 보이고, 사용자가 할 일을 못 찾는다.
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            creds = raw[OAUTH_KEY]
            if not creds.get("accessToken"):
                raise KeyError("accessToken missing")
            return creds
        except (OSError, json.JSONDecodeError, KeyError, TypeError, AttributeError) as err:
            # 원인을 문구에 붙이지 않는다. 이 문자열은 그대로 오버레이 둘째 줄과
            # 트레이 툴팁이 되는데, 붙이면 오버레이는 조용히 잘리고 툴팁은
            # 128자(szTip)를 넘는 순간 ValueError로 갱신 루프를 멈춘다.
            # 진단에 필요한 원인은 __cause__에 그대로 남는다.
            raise ReloginRequired(RELOGIN_MSG) from err
