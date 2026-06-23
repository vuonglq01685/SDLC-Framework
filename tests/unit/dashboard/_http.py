"""HTTP helpers for dashboard integration tests."""

from __future__ import annotations

import urllib.error
import urllib.request


def http_get(
    base_url: str,
    path: str,
    *,
    port: int,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    """Perform a GET and return (status, response_headers, body)."""
    url = f"{base_url}{path}"
    req_headers = {"Host": f"127.0.0.1:{port}"}
    if headers:
        req_headers.update(headers)
    request = urllib.request.Request(url, headers=req_headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            status = response.status
            resp_headers = {k.lower(): v for k, v in response.headers.items()}
            body = response.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        resp_headers = {k.lower(): v for k, v in exc.headers.items()}
        body = exc.read()
    return status, resp_headers, body


def http_request(
    base_url: str,
    path: str,
    *,
    method: str,
    port: int,
    headers: dict[str, str] | None = None,
    body: bytes = b"",
) -> tuple[int, dict[str, str], bytes]:
    url = f"{base_url}{path}"
    req_headers = {"Host": f"127.0.0.1:{port}"}
    if headers:
        req_headers.update(headers)
    request = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            status = response.status
            resp_headers = {k.lower(): v for k, v in response.headers.items()}
            resp_body = response.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        resp_headers = {k.lower(): v for k, v in exc.headers.items()}
        resp_body = exc.read()
    return status, resp_headers, resp_body
