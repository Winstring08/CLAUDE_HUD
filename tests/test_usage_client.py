import json
from datetime import datetime, timezone

import pytest

from claude_usage_overlay.http_client import HttpResponse
from claude_usage_overlay.models import RateLimited, SchemaChanged, Unauthorized
from claude_usage_overlay.usage_client import fetch_usage

NOW = datetime(2026, 8, 10, 3, 25, tzinfo=timezone.utc)

# 2026-08-10 실측 응답을 줄인 것. 코드네임 필드와 limits[]는 실제로 오는 형태 그대로 둔다.
BODY = {
    "five_hour": {
        "utilization": 36.0,
        "resets_at": "2026-08-10T05:39:59.273032+00:00",
        "limit_dollars": None,
    },
    "seven_day": {"utilization": 17.0, "resets_at": "2026-08-12T16:59:59.273052+00:00"},
    "seven_day_opus": None,
    "tangelo": None,
    "iguana_necktie": None,
    "nimbus_quill": {"utilization": 0.0, "resets_at": None},
    "limits": [
        {
            "kind": "session",
            "group": "session",
            "percent": 36,
            "severity": "normal",
            "is_active": True,
        },
        {
            "kind": "weekly_scoped",
            "group": "weekly",
            "percent": 6,
            "scope": {"model": {"id": None, "display_name": "Fable"}, "surface": None},
        },
    ],
    "spend": {"used": {"amount_minor": 0}, "percent": 0},
    "member_dashboard_available": False,
}


def responder(status, body, headers=None):
    payload = body if isinstance(body, bytes) else json.dumps(body).encode()
    return lambda *a, **k: HttpResponse(status, payload, headers or {})


def test_parses_five_hour_and_seven_day():
    snap = fetch_usage("tok", request_fn=responder(200, BODY), now=lambda: NOW)
    assert snap.five_hour_pct == 36.0
    assert snap.seven_day_pct == 17.0
    assert snap.resets_at == datetime(2026, 8, 10, 5, 39, 59, 273032, tzinfo=timezone.utc)
    assert snap.fetched_at == NOW


def test_unknown_fields_are_ignored():
    """코드네임 필드는 예고 없이 늘어난다. 새 키가 생겨도 형식 변경이 아니다."""
    body = dict(BODY)
    body["brand_new_codename"] = {"utilization": 99.0}
    body["another_one"] = None
    snap = fetch_usage("tok", request_fn=responder(200, body), now=lambda: NOW)
    assert snap.five_hour_pct == 36.0


def test_null_resets_at_becomes_none():
    """사용량 0인 새 창에서는 resets_at이 null이다. 사용률은 그대로 쓴다."""
    body = {"five_hour": {"utilization": 0.0, "resets_at": None}}
    snap = fetch_usage("tok", request_fn=responder(200, body), now=lambda: NOW)
    assert snap.resets_at is None
    assert snap.five_hour_pct == 0.0


def test_missing_resets_at_key_becomes_none():
    body = {"five_hour": {"utilization": 42.0}}
    snap = fetch_usage("tok", request_fn=responder(200, body), now=lambda: NOW)
    assert snap.resets_at is None
    assert snap.five_hour_pct == 42.0


def test_unparseable_resets_at_becomes_none_not_schema_changed():
    """시각 포맷이 바뀌어도 사용률은 멀쩡하다. 카운트다운만 포기한다."""
    body = {"five_hour": {"utilization": 42.0, "resets_at": "5시간 뒤"}}
    snap = fetch_usage("tok", request_fn=responder(200, body), now=lambda: NOW)
    assert snap.resets_at is None
    assert snap.five_hour_pct == 42.0


def test_resets_at_without_an_offset_is_read_as_utc():
    """오프셋이 빠진 형태로 오면 tz-naive가 된다. 그대로 흘리면 안 된다.

    오버레이는 tz-aware now와 이 값을 매초 뺀다. naive가 섞이면
    TypeError로 화면이 얼어붙는데, tkinter after 콜백 안이라 스택트레이스도
    안 남는다. 여기서 UTC로 못박는다.
    """
    body = {"five_hour": {"utilization": 42.0, "resets_at": "2026-08-10T05:40:00.564898"}}
    snap = fetch_usage("tok", request_fn=responder(200, body), now=lambda: NOW)
    assert snap.resets_at is not None
    assert snap.resets_at.tzinfo is not None
    assert (snap.resets_at - NOW).total_seconds() > 0   # tz-aware와 뺄 수 있다


def test_sends_required_headers():
    seen = {}

    def spy(method, url, headers, json_body=None, timeout=10.0):
        seen.update(headers)
        seen["_url"] = url
        return HttpResponse(200, json.dumps(BODY).encode(), {})

    fetch_usage("tok-123", request_fn=spy, now=lambda: NOW)
    assert seen["Authorization"] == "Bearer tok-123"
    assert seen["anthropic-beta"] == "oauth-2025-04-20"
    assert seen["_url"] == "https://api.anthropic.com/api/oauth/usage"


def test_missing_seven_day_is_none():
    body = {"five_hour": BODY["five_hour"], "seven_day": None}
    snap = fetch_usage("tok", request_fn=responder(200, body), now=lambda: NOW)
    assert snap.seven_day_pct is None


def test_429_raises_rate_limited_with_retry_after():
    fn = responder(429, {"error": "rate"}, {"retry-after": "287"})
    with pytest.raises(RateLimited) as exc:
        fetch_usage("tok", request_fn=fn, now=lambda: NOW)
    assert exc.value.retry_after == 287


def test_429_without_header_falls_back_to_300():
    with pytest.raises(RateLimited) as exc:
        fetch_usage("tok", request_fn=responder(429, {}), now=lambda: NOW)
    assert exc.value.retry_after == 300


def test_401_raises_unauthorized():
    with pytest.raises(Unauthorized):
        fetch_usage("tok", request_fn=responder(401, {"error": "auth"}), now=lambda: NOW)


def test_null_five_hour_object_is_read_as_zero():
    """값이 없는 창은 통째로 null로 온다 (tangelo·cinder_cove가 그렇다).

    형식이 바뀐 게 아니라 쓴 게 없다는 뜻이므로 0%로 읽는다. 여기서
    SCHEMA_ERROR를 띄우면 사용량 0인 가장 평화로운 순간에 경고가 뜬다.
    """
    body = {"five_hour": None, "seven_day": {"utilization": 3.0}}
    snap = fetch_usage("tok", request_fn=responder(200, body), now=lambda: NOW)
    assert snap.five_hour_pct == 0.0
    assert snap.resets_at is None
    assert snap.seven_day_pct == 3.0


def test_missing_five_hour_key_raises_schema_changed():
    """null로 오는 것과 키가 사라진 것은 다르다. 후자는 형식 변경이다."""
    with pytest.raises(SchemaChanged):
        fetch_usage("tok", request_fn=responder(200, {"seven_day": None}), now=lambda: NOW)


def test_null_five_hour_utilization_raises_schema_changed():
    """객체는 왔는데 그 안의 숫자가 없다. 보여줄 값이 사라진 것이므로 위반이다."""
    body = {"five_hour": {"utilization": None}}
    with pytest.raises(SchemaChanged):
        fetch_usage("tok", request_fn=responder(200, body), now=lambda: NOW)


def test_invalid_json_raises_schema_changed():
    with pytest.raises(SchemaChanged):
        fetch_usage("tok", request_fn=responder(200, b"not json"), now=lambda: NOW)


def test_unexpected_status_raises_schema_changed():
    with pytest.raises(SchemaChanged):
        fetch_usage("tok", request_fn=responder(500, {}), now=lambda: NOW)
