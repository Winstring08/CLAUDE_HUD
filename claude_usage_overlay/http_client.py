"""urllib 어댑터. 다른 모듈은 urllib를 직접 쓰지 않는다."""

import json
import urllib.error
from dataclasses import dataclass
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes
    headers: dict[str, str]


def _normalize(headers) -> dict[str, str]:
    return {str(k).lower(): str(v) for k, v in dict(headers).items()}


def request(
    method: str,
    url: str,
    headers: dict[str, str],
    json_body: dict | None = None,
    timeout: float = 10.0,
) -> HttpResponse:
    """4xx/5xx에서도 예외를 던지지 않는다. 429의 retry-after를 읽어야 하기 때문."""
    data = None
    send_headers = dict(headers)
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        send_headers.setdefault("Content-Type", "application/json")

    req = Request(url, data=data, headers=send_headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as res:
            return HttpResponse(
                status=res.status, body=res.read(), headers=_normalize(res.headers)
            )
    except urllib.error.HTTPError as err:
        return HttpResponse(
            status=err.code, body=err.read(), headers=_normalize(err.headers)
        )
