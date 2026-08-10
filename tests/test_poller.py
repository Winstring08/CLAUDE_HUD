from datetime import datetime, timedelta, timezone

from claude_usage_overlay.config import Config
from claude_usage_overlay.models import (
    RateLimited,
    ReloginRequired,
    SchemaChanged,
    Status,
    Unauthorized,
    UsageSnapshot,
)
from claude_usage_overlay.poller import Poller

NOW = datetime(2026, 8, 10, 3, 25, tzinfo=timezone.utc)


class FakeStore:
    def __init__(self, token="tok", error=None):
        self.token = token
        self.error = error
        self.calls = 0

    def get_access_token(self):
        self.calls += 1
        if self.error:
            raise self.error
        return self.token


def snapshot(at=NOW, pct=23.0):
    return UsageSnapshot(
        five_hour_pct=pct,
        resets_at=at + timedelta(hours=2),
        seven_day_pct=15.0,
        fetched_at=at,
    )


def make(fetch_fn, store=None, now=NOW):
    clock = {"t": now}
    p = Poller(
        store=store or FakeStore(),
        config=Config(poll_seconds=300),
        fetch_fn=fetch_fn,
        now=lambda: clock["t"],
    )
    return p, clock


def test_success_produces_ok_state_and_base_delay():
    p, _ = make(lambda token, **k: snapshot())
    delay = p.step()
    assert delay == 300
    assert p.state().status is Status.OK
    assert p.state().snapshot.five_hour_pct == 23.0


def test_failure_after_success_is_stale_and_keeps_last_snapshot():
    calls = {"n": 0}

    def flaky(token, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return snapshot()
        raise OSError("network down")

    p, clock = make(flaky)
    p.step()
    clock["t"] = NOW + timedelta(minutes=14)
    delay = p.step()

    state = p.state()
    assert state.status is Status.STALE
    assert state.snapshot.five_hour_pct == 23.0   # 마지막 값을 유지한다
    assert state.detail == "14분째 갱신 실패"
    assert delay == 300                            # 첫 실패는 기본 주기


def test_backoff_doubles_and_caps():
    p, _ = make(lambda token, **k: (_ for _ in ()).throw(OSError("down")))
    assert p.step() == 300     # 1회 실패
    assert p.step() == 600     # 2회
    assert p.step() == 1200    # 3회
    assert p.step() == 1800    # 4회 — 상한
    assert p.step() == 1800    # 5회 — 상한 유지


def test_success_resets_backoff():
    calls = {"n": 0}

    def flaky(token, **k):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise OSError("down")
        return snapshot()

    p, _ = make(flaky)
    p.step()
    p.step()
    assert p.step() == 300


def test_rate_limited_honors_retry_after():
    p, _ = make(lambda token, **k: (_ for _ in ()).throw(RateLimited(287)))
    delay = p.step()
    assert delay == 292                      # retry_after + 5초 여유
    assert p.state().status is Status.RATE_LIMITED


def test_request_now_is_ignored_during_the_rate_limit_penalty():
    """스펙 8장은 retry-after까지 호출하지 않기로 했다.

    트레이 메뉴가 유일한 조작 수단이라 사용자는 답답할 때 "지금 갱신"을 누른다.
    그 버튼이 벌칙 구간을 깨우면 429가 또 나고 벌칙만 길어진다.
    """
    p, clock = make(lambda token, **k: (_ for _ in ()).throw(RateLimited(287)))
    p.step()

    p.request_now()
    assert not p._wake.is_set()              # 무시됐다

    clock["t"] = NOW + timedelta(seconds=293)   # 벌칙이 끝난 뒤
    p.request_now()
    assert p._wake.is_set()


def test_request_now_works_when_not_rate_limited():
    p, _ = make(lambda token, **k: snapshot())
    p.step()
    p.request_now()
    assert p._wake.is_set()


def test_unauthorized_retries_before_giving_up():
    """만료 직전 토큰과 Claude Code의 갱신이 겹치는 정상 경합이 있다.
    CredentialStore가 매번 파일을 다시 읽으므로 다음 틱이면 낫는다."""
    p, _ = make(lambda token, **k: (_ for _ in ()).throw(Unauthorized()))

    p.step()
    assert p.state().status is Status.STALE
    p.step()
    assert p.state().status is Status.STALE

    p.step()  # 3회 연속 — 경합이 아니라 인증 문제다
    assert p.state().status is Status.RELOGIN
    assert "claude auth login" in p.state().detail


def test_unauthorized_retry_does_not_back_off():
    """401 재시도는 기본 주기를 쓴다.

    백오프를 태우면 '다음 틱'이 5분에서 10분, 20분으로 늘어나 3회를 채우는 데
    35분이 걸린다. 5분이면 나을 경합을 위해 만든 유예가 회복을 늦추면 안 된다.
    """
    p, _ = make(lambda token, **k: (_ for _ in ()).throw(Unauthorized()))
    assert p.step() == 300
    assert p.step() == 300


def test_unauthorized_does_not_pollute_the_failure_counter():
    """인증 경합과 네트워크 단절은 다른 사건이다. 카운터를 공유하면 안 된다."""
    calls = {"n": 0}

    def auth_then_network(token, **k):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise Unauthorized()
        raise OSError("down")

    p, _ = make(auth_then_network)
    p.step()
    p.step()
    assert p.step() == 300   # 첫 네트워크 실패다. 앞선 401 두 번은 세지 않았다


def test_success_resets_the_unauthorized_counter():
    calls = {"n": 0}

    def flaky(token, **k):
        calls["n"] += 1
        if calls["n"] in (1, 2, 4, 5):
            raise Unauthorized()
        return snapshot()

    p, _ = make(flaky)
    p.step()
    p.step()
    p.step()                                  # 성공 — 카운터 초기화
    p.step()
    p.step()
    assert p.state().status is Status.STALE   # 다시 2회일 뿐이므로 아직 아니다


def test_relogin_message_from_the_store_is_shown_as_is():
    """무엇을 해야 하는지는 credentials가 정한다. 폴러는 그대로 전달한다."""
    store = FakeStore(error=ReloginRequired("토큰 만료 — Claude Code를 한 번 실행하세요"))
    p, _ = make(lambda token, **k: snapshot(), store=store)
    p.step()

    state = p.state()
    assert state.status is Status.RELOGIN
    assert state.detail == "토큰 만료 — Claude Code를 한 번 실행하세요"
    assert state.snapshot is None


def test_relogin_does_not_back_off():
    """자격증명 확인은 로컬 파일 읽기다. 늦출 이유가 없다.

    백오프를 태우면 사용자가 Claude Code를 실행해 고쳐놓은 것을 최대 30분
    뒤에야 알아챈다. README는 "한 번 실행하면 낫는다"고 약속했다.
    """
    store = FakeStore(error=ReloginRequired("토큰 만료 — Claude Code를 한 번 실행하세요"))
    p, _ = make(lambda token, **k: snapshot(), store=store)
    assert [p.step() for _ in range(4)] == [300, 300, 300, 300]


def test_relogin_after_three_401s_does_not_back_off_either():
    """401로 도달한 RELOGIN도 같다. 회복 경로가 같으니 지연도 같아야 한다."""
    p, _ = make(lambda token, **k: (_ for _ in ()).throw(Unauthorized()))
    assert [p.step() for _ in range(4)] == [300, 300, 300, 300]
    assert p.state().status is Status.RELOGIN


def test_relogin_recovers_on_the_next_tick():
    """사용자가 Claude Code를 실행하면 다음 틱에 낫는다."""
    store = FakeStore(error=ReloginRequired("토큰 만료"))
    p, _ = make(lambda token, **k: snapshot(), store=store)
    p.step()
    assert p.state().status is Status.RELOGIN

    store.error = None                       # Claude Code가 파일을 갱신했다
    p.step()
    assert p.state().status is Status.OK


def test_schema_change_is_reported_not_guessed():
    p, _ = make(lambda token, **k: (_ for _ in ()).throw(SchemaChanged("no five_hour")))
    p.step()
    assert p.state().status is Status.SCHEMA_ERROR
    assert p.state().snapshot is None


def test_initial_state_before_first_step():
    p, _ = make(lambda token, **k: snapshot())
    assert p.state().status is Status.STALE
    assert p.state().snapshot is None
