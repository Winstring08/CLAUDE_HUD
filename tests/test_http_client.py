import io
import urllib.error

from claude_usage_overlay.http_client import HttpResponse, request


class FakeHTTPError(urllib.error.HTTPError):
    def __init__(self, status, body, headers):
        super().__init__("http://x", status, "err", headers, io.BytesIO(body))


def test_returns_body_and_normalized_headers(monkeypatch):
    class FakeResponse:
        status = 200
        headers = {"Retry-After": "12", "Content-Type": "application/json"}

        def read(self):
            return b'{"ok": true}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        "claude_usage_overlay.http_client.urlopen",
        lambda req, timeout: FakeResponse(),
    )

    res = request("GET", "http://x", {"Authorization": "Bearer t"})
    assert isinstance(res, HttpResponse)
    assert res.status == 200
    assert res.body == b'{"ok": true}'
    assert res.headers["retry-after"] == "12"


def test_http_error_is_returned_not_raised(monkeypatch):
    def boom(req, timeout):
        raise FakeHTTPError(429, b'{"error": "rate"}', {"Retry-After": "287"})

    monkeypatch.setattr("claude_usage_overlay.http_client.urlopen", boom)

    res = request("GET", "http://x", {})
    assert res.status == 429
    assert res.headers["retry-after"] == "287"
    assert b"rate" in res.body
