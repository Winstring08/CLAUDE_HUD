"""자격증명 파일 읽기.

이 파일에 쓰지 않는다. 토큰 갱신 API도 호출하지 않는다.

refreshToken은 갱신할 때마다 회전한다. 우리가 회전시키면 옛 토큰을 메모리에
들고 있는 Claude Code와 데스크톱 앱이 다음 갱신 때 죽는다. 사용량을 5분 빨리
보려고 사용자의 인증을 깨뜨릴 수는 없다. 갱신은 Claude Code에 맡기고 우리는
편승한다. (스펙 9장)

대가는 하나다 — Claude Code를 8시간 넘게 쓰지 않으면 우리 토큰도 만료된다.
그때는 숫자를 지어내지 않고 사용자에게 무엇을 해야 하는지 말한다.
"""

import json
import os
import time
from pathlib import Path
from typing import Callable

from .models import ReloginRequired

CREDENTIALS_PATH = Path(os.environ.get("USERPROFILE", str(Path.home()))) / ".claude" / ".credentials.json"
OAUTH_KEY = "claudeAiOauth"

# 화면에 그대로 나가는 문구다. 짧게 유지한다 — 오버레이 창 폭이 가장 긴
# 문구에서 역산되므로, 여기가 길면 평소 화면에 빈 공간만 늘어난다.
RELOGIN_MSG = "재로그인 필요 — claude auth login"
STALE_TOKEN_MSG = "토큰 만료 — Claude Code 실행"


def _now_ms() -> int:
    return int(time.time() * 1000)


class CredentialStore:
    def __init__(
        self,
        path: Path | None = None,
        now_ms: Callable[[], int] = _now_ms,
    ) -> None:
        self._path = path or CREDENTIALS_PATH
        self._now_ms = now_ms

    # --- 공개 인터페이스 -------------------------------------------------

    def get_access_token(self) -> str:
        """유효한 accessToken을 돌려준다. 없으면 ReloginRequired.

        호출할 때마다 파일을 다시 읽는다. 캐시하면 Claude Code가 갱신한
        새 토큰을 놓친다.
        """
        creds = self._read()
        now = self._now_ms()

        refresh_expires_at = self._expiry_ms(creds.get("refreshTokenExpiresAt"))
        if refresh_expires_at is not None and refresh_expires_at <= now:
            raise ReloginRequired(RELOGIN_MSG)

        expires_at = self._expiry_ms(creds.get("expiresAt"))
        if expires_at is None or expires_at <= now:
            # refreshToken은 살아 있다. Claude Code를 한 번 쓰면 저절로 갱신된다.
            raise ReloginRequired(STALE_TOKEN_MSG)

        return creds["accessToken"]

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
