import json

import pytest

from claude_usage_overlay.credentials import (
    RELOGIN_MSG,
    REFRESH_MARGIN_MS,
    STALE_TOKEN_MSG,
    CredentialStore,
)
from claude_usage_overlay.http_client import HttpResponse
from claude_usage_overlay.models import ReloginRequired

NOW_MS = 1_786_331_000_000
HOUR_MS = 3_600_000


def _explode(*args, **kwargs):
    """네트워크를 쓰면 안 되는 경로에 꽂는다."""
    raise AssertionError("여기서는 토큰 갱신을 호출하면 안 된다")


def _issuer(access="acc-new", refresh="ref-new", status=200, calls=None, **extra):
    """갱신 엔드포인트 흉내. 호출 내역을 calls에 남긴다."""
    body = {
        "access_token": access,
        "refresh_token": refresh,
        "expires_in": 28800,
        "refresh_token_expires_in": 2_585_692,
        **extra,
    }

    def fake(method, url, headers, json_body=None, timeout=10.0):
        if calls is not None:
            calls.append({"url": url, "body": json_body, "timeout": timeout})
        return HttpResponse(status, json.dumps(body).encode(), {})

    return fake


def write_creds(path, *, access="acc-old", refresh="ref-old", expires_at=None, refresh_expires_at=None):
    path.write_text(
        json.dumps(
            {
                "claudeAiOauth": {
                    "accessToken": access,
                    "refreshToken": refresh,
                    "expiresAt": expires_at if expires_at is not None else NOW_MS + 8 * HOUR_MS,
                    "refreshTokenExpiresAt": refresh_expires_at
                    if refresh_expires_at is not None
                    else NOW_MS + 30 * 24 * HOUR_MS,
                    "scopes": ["user:profile"],
                    "subscriptionType": "max",
                }
            }
        ),
        encoding="utf-8",
    )


def test_valid_token_is_returned(tmp_path):
    p = tmp_path / ".credentials.json"
    write_creds(p)
    store = CredentialStore(path=p, now_ms=lambda: NOW_MS)
    assert store.get_access_token() == "acc-old"


def test_file_is_reread_every_call(tmp_path):
    """캐시하지 않는다. Claude Code가 파일을 갱신하면 다음 호출에서 바로 반영된다."""
    p = tmp_path / ".credentials.json"
    write_creds(p, access="acc-old")
    store = CredentialStore(path=p, now_ms=lambda: NOW_MS)
    assert store.get_access_token() == "acc-old"

    write_creds(p, access="acc-from-cli")
    assert store.get_access_token() == "acc-from-cli"


def test_does_not_touch_the_file_when_the_token_is_healthy(tmp_path):
    """갱신할 이유가 없으면 파일을 건드리지 않는다.

    refreshToken은 갱신할 때마다 회전한다. 회전은 그 자체가 위험이므로
    꼭 필요할 때만 한다 — 만료 30분 밖이면 그냥 읽고 끝낸다.
    """
    p = tmp_path / ".credentials.json"
    write_creds(p, expires_at=NOW_MS + 8 * HOUR_MS)
    before = p.read_bytes()

    store = CredentialStore(path=p, now_ms=lambda: NOW_MS, request_fn=_explode)
    store.get_access_token()

    assert p.read_bytes() == before
    assert not list(p.parent.glob("*.tmp"))


def test_does_not_touch_the_file_when_relogin_is_needed(tmp_path):
    """refreshToken까지 죽었으면 갱신해도 소용없다. 파일을 건드리지 않는다."""
    p = tmp_path / ".credentials.json"
    write_creds(p, expires_at=NOW_MS - 1000, refresh_expires_at=NOW_MS - 1000)
    before = p.read_bytes()

    store = CredentialStore(path=p, now_ms=lambda: NOW_MS, request_fn=_explode)
    with pytest.raises(ReloginRequired):
        store.get_access_token()

    assert p.read_bytes() == before
    assert not list(p.parent.glob("*.tmp"))


def test_expired_access_token_is_refreshed(tmp_path):
    """accessToken만 만료: refreshToken이 살아 있으니 우리가 갱신한다.

    데스크톱 앱은 이 파일을 갱신하지 않는다(실측). 편승할 대상이 없다.
    """
    p = tmp_path / ".credentials.json"
    write_creds(p, expires_at=NOW_MS - 1000)
    store = CredentialStore(path=p, now_ms=lambda: NOW_MS, request_fn=_issuer())

    assert store.get_access_token() == "acc-new"


def test_expired_refresh_token_asks_for_relogin(tmp_path):
    """refreshToken까지 만료: 사용자가 직접 로그인해야 한다."""
    p = tmp_path / ".credentials.json"
    write_creds(p, expires_at=NOW_MS - 1000, refresh_expires_at=NOW_MS - 1000)
    store = CredentialStore(path=p, now_ms=lambda: NOW_MS)

    with pytest.raises(ReloginRequired) as exc:
        store.get_access_token()
    assert "claude auth login" in str(exc.value)


def test_missing_file_asks_for_relogin(tmp_path):
    store = CredentialStore(path=tmp_path / "nope.json", now_ms=lambda: NOW_MS)
    with pytest.raises(ReloginRequired) as exc:
        store.get_access_token()
    assert "claude auth login" in str(exc.value)


def test_broken_file_asks_for_relogin(tmp_path):
    p = tmp_path / ".credentials.json"
    p.write_text("{ not json", encoding="utf-8")
    store = CredentialStore(path=p, now_ms=lambda: NOW_MS)
    with pytest.raises(ReloginRequired):
        store.get_access_token()


def test_missing_oauth_key_asks_for_relogin(tmp_path):
    p = tmp_path / ".credentials.json"
    p.write_text(json.dumps({"somethingElse": {}}), encoding="utf-8")
    store = CredentialStore(path=p, now_ms=lambda: NOW_MS)
    with pytest.raises(ReloginRequired):
        store.get_access_token()


def test_oauth_key_that_is_not_an_object_asks_for_relogin(tmp_path):
    """손상된 파일이 네트워크 오류처럼 보이면 안 된다.

    .get에서 AttributeError가 새어 나가면 폴러의 except Exception이 받아
    "N분째 갱신 실패"를 띄운다. 사용자는 인터넷을 의심하고 진짜 원인은 못 본다.
    """
    p = tmp_path / ".credentials.json"
    p.write_text(json.dumps({"claudeAiOauth": "손상됨"}), encoding="utf-8")
    store = CredentialStore(path=p, now_ms=lambda: NOW_MS)
    with pytest.raises(ReloginRequired):
        store.get_access_token()


def test_missing_refresh_expiry_is_not_treated_as_expired(tmp_path):
    """refreshTokenExpiresAt가 없는 형식이어도 accessToken이 살아 있으면 쓴다."""
    p = tmp_path / ".credentials.json"
    p.write_text(
        json.dumps(
            {"claudeAiOauth": {"accessToken": "acc", "expiresAt": NOW_MS + HOUR_MS}}
        ),
        encoding="utf-8",
    )
    store = CredentialStore(path=p, now_ms=lambda: NOW_MS)
    assert store.get_access_token() == "acc"


def test_unreadable_expiry_does_not_look_like_a_network_failure(tmp_path):
    """만료 시각이 숫자가 아니면 int()가 ValueError를 던진다.

    그게 새어 나가면 폴러의 except Exception이 받아 "N분째 갱신 실패"를 띄운다.
    파일 형식이 바뀐 것인데 화면은 인터넷 문제라고 말하게 된다.
    """
    p = tmp_path / ".credentials.json"
    for broken in ("2026-08-10T20:22:39Z", [], {"ms": 1}):
        for field in ("expiresAt", "refreshTokenExpiresAt"):
            creds = {"accessToken": "acc", "expiresAt": NOW_MS + HOUR_MS}
            creds[field] = broken
            p.write_text(json.dumps({"claudeAiOauth": creds}), encoding="utf-8")
            store = CredentialStore(path=p, now_ms=lambda: NOW_MS)
            with pytest.raises(ReloginRequired):
                store.get_access_token()


def test_missing_expiry_is_treated_as_expired(tmp_path):
    """expiresAt이 아예 없으면 유효하다고 볼 근거가 없다. 지어내지 않는다."""
    p = tmp_path / ".credentials.json"
    p.write_text(json.dumps({"claudeAiOauth": {"accessToken": "acc"}}), encoding="utf-8")
    store = CredentialStore(path=p, now_ms=lambda: NOW_MS, request_fn=_explode)
    with pytest.raises(ReloginRequired):
        store.get_access_token()


def test_message_never_carries_the_raw_exception(tmp_path):
    """이 문구는 그대로 오버레이 둘째 줄과 트레이 툴팁이 된다.

    예외 텍스트를 붙이면 오버레이는 조용히 잘리고, 트레이는 128자(szTip)를
    넘는 순간 ValueError를 던져 메인 스레드의 갱신 루프를 멈춘다.
    원인은 화면이 아니라 __cause__에 남긴다.
    """
    p = tmp_path / ".credentials.json"
    for broken in ("{ not json", json.dumps({"claudeAiOauth": "손상됨"})):
        p.write_text(broken, encoding="utf-8")
        store = CredentialStore(path=p, now_ms=lambda: NOW_MS)
        with pytest.raises(ReloginRequired) as exc:
            store.get_access_token()
        assert str(exc.value) == RELOGIN_MSG
        assert exc.value.__cause__ is not None      # 원인은 남아 있다

    assert len(f"Claude 사용량\n{RELOGIN_MSG}") <= 128
    assert len(f"Claude 사용량\n{STALE_TOKEN_MSG}") <= 128


# --- 토큰 갱신 -----------------------------------------------------------
#
# 읽기 전용을 포기하고 갱신을 넣은 이유는 실측이다. accessToken이 만료된 뒤에도
# 데스크톱 앱은 멀쩡히 도는데 .credentials.json은 8시간 전 그대로였다.
# 편승할 대상이 없으므로 우리가 갱신한다. 아래 테스트들이 스펙 9장의 방어 셋을
# 지킨다 — 원자적 쓰기 · 갱신 직전 재읽기 · 만료 30분 전에만.


def _read_creds(path):
    return json.loads(path.read_text(encoding="utf-8"))["claudeAiOauth"]


def test_refresh_writes_both_new_tokens(tmp_path):
    p = tmp_path / ".credentials.json"
    write_creds(p, expires_at=NOW_MS - 1000)
    store = CredentialStore(path=p, now_ms=lambda: NOW_MS, request_fn=_issuer())

    assert store.get_access_token() == "acc-new"
    saved = _read_creds(p)
    assert saved["accessToken"] == "acc-new"
    assert saved["refreshToken"] == "ref-new", "회전한 refreshToken을 저장해야 다음 갱신이 된다"
    assert saved["expiresAt"] == NOW_MS + 28800 * 1000


def test_refresh_keeps_fields_it_does_not_understand(tmp_path):
    """이 파일은 우리 것이 아니다. 모르는 키를 지우면 남의 기능이 깨진다."""
    p = tmp_path / ".credentials.json"
    raw = {
        "claudeAiOauth": {
            "accessToken": "acc-old",
            "refreshToken": "ref-old",
            "expiresAt": NOW_MS - 1000,
            "subscriptionType": "max",
            "rateLimitTier": "default_claude_max_5x",
            "미래에생길필드": "건드리지마",
        },
        "다른최상위키": {"보존": True},
    }
    p.write_text(json.dumps(raw), encoding="utf-8")

    CredentialStore(path=p, now_ms=lambda: NOW_MS, request_fn=_issuer()).get_access_token()

    after = json.loads(p.read_text(encoding="utf-8"))
    assert after["다른최상위키"] == {"보존": True}
    assert after["claudeAiOauth"]["subscriptionType"] == "max"
    assert after["claudeAiOauth"]["rateLimitTier"] == "default_claude_max_5x"
    assert after["claudeAiOauth"]["미래에생길필드"] == "건드리지마"


def test_refresh_leaves_no_temp_file(tmp_path):
    """방어 1: 임시 파일에 쓰고 os.replace. 찌꺼기가 남으면 안 된다."""
    p = tmp_path / ".credentials.json"
    write_creds(p, expires_at=NOW_MS - 1000)
    CredentialStore(path=p, now_ms=lambda: NOW_MS, request_fn=_issuer()).get_access_token()
    assert not list(tmp_path.glob("*.tmp"))


def test_refresh_is_skipped_when_someone_else_just_did_it(tmp_path):
    """방어 2: 갱신 직전에 다시 읽는다.

    그 사이 다른 클라이언트가 갱신했으면 우리는 회전시키지 않는다.
    회전을 한 번 덜 하는 것이 곧 사고 확률을 줄이는 일이다.
    """
    p = tmp_path / ".credentials.json"
    write_creds(p, expires_at=NOW_MS - 1000)

    calls = []

    def swap_then_issue(method, url, headers, json_body=None, timeout=10.0):
        raise AssertionError("남이 이미 갱신했으면 호출하면 안 된다")

    class Racing(CredentialStore):
        def _read(self):
            creds = super()._read()
            # 첫 읽기 뒤, 갱신 직전 재읽기 전에 다른 프로세스가 갱신한 상황
            write_creds(p, access="acc-from-other", expires_at=NOW_MS + 8 * HOUR_MS)
            return creds

    store = Racing(path=p, now_ms=lambda: NOW_MS, request_fn=swap_then_issue)
    assert store.get_access_token() == "acc-from-other"
    assert calls == []


def test_refresh_starts_before_the_token_actually_expires(tmp_path):
    """방어 3: 만료 30분 전부터 갱신한다. 폴링 한 번을 만료된 토큰으로 날리지 않는다."""
    p = tmp_path / ".credentials.json"
    calls = []

    # 만료 29분 전 — 갱신한다
    write_creds(p, expires_at=NOW_MS + REFRESH_MARGIN_MS - 60_000)
    store = CredentialStore(path=p, now_ms=lambda: NOW_MS, request_fn=_issuer(calls=calls))
    assert store.get_access_token() == "acc-new"
    assert len(calls) == 1

    # 만료 31분 전 — 아직 그대로 쓴다
    write_creds(p, access="acc-still-good", expires_at=NOW_MS + REFRESH_MARGIN_MS + 60_000)
    store = CredentialStore(path=p, now_ms=lambda: NOW_MS, request_fn=_explode)
    assert store.get_access_token() == "acc-still-good"


def test_network_failure_keeps_using_a_live_token(tmp_path):
    """갱신에 실패해도 살아 있는 토큰은 버리지 않는다.

    네트워크가 잠깐 끊긴 것과 인증이 죽은 것은 다르다. 30분 여유가 이 몫이다.
    """
    p = tmp_path / ".credentials.json"
    write_creds(p, access="acc-live", expires_at=NOW_MS + 10 * 60 * 1000)   # 10분 남음

    def down(*a, **k):
        raise OSError("network down")

    store = CredentialStore(path=p, now_ms=lambda: NOW_MS, request_fn=down)
    assert store.get_access_token() == "acc-live"
    assert _read_creds(p)["refreshToken"] == "ref-old", "실패했으면 파일을 건드리지 않는다"


def test_network_failure_on_an_expired_token_reports_it(tmp_path):
    """이미 만료됐는데 갱신도 실패하면 숨길 수 없다."""
    p = tmp_path / ".credentials.json"
    write_creds(p, expires_at=NOW_MS - 1000)

    def down(*a, **k):
        raise OSError("network down")

    store = CredentialStore(path=p, now_ms=lambda: NOW_MS, request_fn=down)
    with pytest.raises(ReloginRequired) as exc:
        store.get_access_token()
    assert str(exc.value) == STALE_TOKEN_MSG


def test_rejected_refresh_token_asks_for_relogin(tmp_path):
    """400/401은 refreshToken이 죽었다는 뜻이다. 다시 시도해도 같다."""
    p = tmp_path / ".credentials.json"
    for status in (400, 401, 403):
        write_creds(p, expires_at=NOW_MS - 1000)
        store = CredentialStore(
            path=p, now_ms=lambda: NOW_MS, request_fn=_issuer(status=status)
        )
        with pytest.raises(ReloginRequired) as exc:
            store.get_access_token()
        assert str(exc.value) == RELOGIN_MSG
        assert _read_creds(p)["refreshToken"] == "ref-old", "거부됐으면 쓰지 않는다"


def test_incomplete_response_is_not_saved(tmp_path):
    """토큰이 빠진 응답을 저장하면 다음 실행부터 인증이 통째로 죽는다."""
    p = tmp_path / ".credentials.json"
    write_creds(p, expires_at=NOW_MS - 1000)

    def half(method, url, headers, json_body=None, timeout=10.0):
        return HttpResponse(200, json.dumps({"access_token": "acc-new"}).encode(), {})

    store = CredentialStore(path=p, now_ms=lambda: NOW_MS, request_fn=half)
    with pytest.raises(ReloginRequired):
        store.get_access_token()
    assert _read_creds(p)["accessToken"] == "acc-old"


def test_refresh_request_shape(tmp_path):
    """스펙 3.3에서 실측한 요청 형식 그대로 보낸다."""
    p = tmp_path / ".credentials.json"
    write_creds(p, refresh="ref-abc", expires_at=NOW_MS - 1000)
    calls = []
    CredentialStore(
        path=p, now_ms=lambda: NOW_MS, request_fn=_issuer(calls=calls)
    ).get_access_token()

    sent = calls[0]
    assert sent["url"] == "https://console.anthropic.com/v1/oauth/token"
    assert sent["body"]["grant_type"] == "refresh_token"
    assert sent["body"]["refresh_token"] == "ref-abc"
    assert sent["body"]["client_id"]
    assert sent["timeout"] >= 20, "갱신은 조회보다 여유를 준다"


def test_scope_string_is_stored_as_a_list(tmp_path):
    """파일은 scopes를 배열로 들고 있는데 응답은 공백으로 이은 문자열이다."""
    p = tmp_path / ".credentials.json"
    write_creds(p, expires_at=NOW_MS - 1000)
    CredentialStore(
        path=p,
        now_ms=lambda: NOW_MS,
        request_fn=_issuer(scope="user:profile user:inference"),
    ).get_access_token()

    assert _read_creds(p)["scopes"] == ["user:profile", "user:inference"]


def test_write_is_checked_before_the_token_is_rotated(tmp_path):
    """저장 못 할 상황이면 **회전을 시작조차 하지 않는다.**

    서버가 새 토큰을 내주는 순간 옛 refreshToken은 무효가 된다. 그때 저장에
    실패하면 양쪽 다 잃고 사용자가 재로그인해야 한다 — 이 프로그램이 입힐 수
    있는 유일한 되돌릴 수 없는 피해다. 미리 걸러내면 그 창이 닫힌다.
    """
    p = tmp_path / ".credentials.json"
    write_creds(p, expires_at=NOW_MS - 1000)
    calls = []

    class Unwritable(CredentialStore):
        def _check_writable(self):
            raise OSError("디스크에 쓸 수 없음")

    store = Unwritable(path=p, now_ms=lambda: NOW_MS, request_fn=_issuer(calls=calls))
    with pytest.raises(ReloginRequired):
        store.get_access_token()

    assert calls == [], "쓸 수 없으면 갱신 요청을 보내면 안 된다"
    assert _read_creds(p)["refreshToken"] == "ref-old"


def test_write_check_leaves_no_probe_file(tmp_path):
    p = tmp_path / ".credentials.json"
    write_creds(p, expires_at=NOW_MS - 1000)
    CredentialStore(path=p, now_ms=lambda: NOW_MS, request_fn=_issuer()).get_access_token()
    assert not list(tmp_path.glob("*.probe"))


def test_write_check_does_not_disturb_the_real_file(tmp_path):
    """탐침이 진짜 파일을 건드리면 그 자체가 사고다."""
    p = tmp_path / ".credentials.json"
    write_creds(p, expires_at=NOW_MS + 8 * HOUR_MS)
    before = p.read_bytes()
    CredentialStore(path=p, now_ms=lambda: NOW_MS)._check_writable()
    assert p.read_bytes() == before
