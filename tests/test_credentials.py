import json

import pytest

from claude_usage_overlay.credentials import (
    RELOGIN_MSG,
    STALE_TOKEN_MSG,
    CredentialStore,
)
from claude_usage_overlay.models import ReloginRequired

NOW_MS = 1_786_331_000_000
HOUR_MS = 3_600_000


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


def test_never_writes_to_the_file(tmp_path):
    """스펙 9장을 지키는 테스트. 어떤 경로로도 파일이 변하면 안 된다."""
    p = tmp_path / ".credentials.json"

    for expires_at in (NOW_MS + 8 * HOUR_MS, NOW_MS - 1000):
        write_creds(p, expires_at=expires_at)
        before = p.read_bytes()
        store = CredentialStore(path=p, now_ms=lambda: NOW_MS)
        try:
            store.get_access_token()
        except ReloginRequired:
            pass
        assert p.read_bytes() == before
        assert not list(p.parent.glob("*.tmp"))


def test_expired_access_token_asks_to_run_claude_code(tmp_path):
    """accessToken만 만료: refreshToken이 살아 있으므로 Claude Code가 고쳐준다."""
    p = tmp_path / ".credentials.json"
    write_creds(p, expires_at=NOW_MS - 1000)
    store = CredentialStore(path=p, now_ms=lambda: NOW_MS)

    with pytest.raises(ReloginRequired) as exc:
        store.get_access_token()
    assert "Claude Code" in str(exc.value)
    assert "auth login" not in str(exc.value)


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
    store = CredentialStore(path=p, now_ms=lambda: NOW_MS)
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
