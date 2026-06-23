"""Security and routing tests for the dashboard server (Story 5.1 AC1, AC4-AC6)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from sdlc.dashboard.server import create_server, validate_bind_host, validate_host_header
from sdlc.errors import SecurityError

from ._http import http_get, http_request

pytestmark = pytest.mark.unit

_NEEDS_SYMLINK = pytest.mark.skipif(
    sys.platform == "win32",
    reason="symlink creation needs privilege on Windows; exercised on the CI POSIX legs",
)


class TestBindHost:
    def test_rejects_zero_zero_zero_zero(self) -> None:
        with pytest.raises(SecurityError, match="dashboard must bind localhost only"):
            validate_bind_host("0.0.0.0")

    def test_create_server_binds_loopback(self, dashboard_project: Path) -> None:
        server = create_server(repo_root=dashboard_project, host="127.0.0.1", port=0)
        host, _port = server.server_address
        assert host == "127.0.0.1"
        server.server_close()


class TestHostHeaderAllowlist:
    @pytest.mark.parametrize(
        "host",
        ["localhost", "127.0.0.1", "[::1]", "localhost:8765", "127.0.0.1:8765", "[::1]:8765"],
    )
    def test_allowed_hosts(self, host: str) -> None:
        assert validate_host_header(host, port=8765) is True

    @pytest.mark.parametrize("host", ["evil.test", "192.168.1.1", "127.0.0.1:9999"])
    def test_disallowed_hosts(self, host: str) -> None:
        assert validate_host_header(host, port=8765) is False

    def test_absent_or_empty_host_rejected(self) -> None:
        # Security branch `if not host_header` (server.py) — CR5.1 review R8.
        assert validate_host_header(None, port=8765) is False
        assert validate_host_header("", port=8765) is False

    def test_forbidden_host_returns_403(self, running_dashboard: tuple[str, int, object]) -> None:
        base_url, port, _ = running_dashboard
        status, _, _ = http_get(base_url, "/state.json", port=port, headers={"Host": "evil.test"})
        assert status == 403


class TestWriteMethods:
    @pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
    def test_write_methods_return_405(
        self, running_dashboard: tuple[str, int, object], method: str
    ) -> None:
        base_url, port, _ = running_dashboard
        status, headers, _ = http_request(base_url, "/state.json", method=method, port=port)
        assert status == 405
        assert headers.get("allow") == "GET, HEAD"


class TestReadMethodFunnel:
    """All verbs funnel through the Host-allowlist; non-GET/HEAD reads → 405 (R1)."""

    def test_head_on_state_json_returns_headers_without_body(
        self, running_dashboard: tuple[str, int, object]
    ) -> None:
        base_url, port, _ = running_dashboard
        status, headers, body = http_request(base_url, "/state.json", method="HEAD", port=port)
        assert status == 200
        assert headers.get("etag", "").startswith("sha256:")
        assert body == b""

    def test_head_with_forbidden_host_returns_403(
        self, running_dashboard: tuple[str, int, object]
    ) -> None:
        base_url, port, _ = running_dashboard
        status, _, _ = http_request(
            base_url, "/state.json", method="HEAD", port=port, headers={"Host": "evil.test"}
        )
        assert status == 403

    def test_options_returns_405_with_allow_header(
        self, running_dashboard: tuple[str, int, object]
    ) -> None:
        base_url, port, _ = running_dashboard
        status, headers, _ = http_request(base_url, "/state.json", method="OPTIONS", port=port)
        assert status == 405
        assert headers.get("allow") == "GET, HEAD"

    def test_options_with_forbidden_host_returns_403(
        self, running_dashboard: tuple[str, int, object]
    ) -> None:
        base_url, port, _ = running_dashboard
        status, _, _ = http_request(
            base_url, "/state.json", method="OPTIONS", port=port, headers={"Host": "evil.test"}
        )
        assert status == 403


class TestStaticContainment:
    def test_serves_index_html(self, running_dashboard: tuple[str, int, object]) -> None:
        base_url, port, _ = running_dashboard
        status, headers, body = http_get(base_url, "/", port=port)
        assert status == 200
        assert "text/html" in headers.get("content-type", "")
        assert b"SDLC Dashboard" in body

    def test_dotdot_escape_returns_404(self, running_dashboard: tuple[str, int, object]) -> None:
        base_url, port, _ = running_dashboard
        status, _, _ = http_get(base_url, "/../server.py", port=port)
        assert status == 404

    def test_missing_static_returns_404(self, running_dashboard: tuple[str, int, object]) -> None:
        base_url, port, _ = running_dashboard
        status, _, _ = http_get(base_url, "/missing-asset.js", port=port)
        assert status == 404

    def test_percent_encoded_static_path_rejected(self, tmp_path: Path) -> None:
        # Explicit rejection of percent-encoded static paths (AC6, CR5.1 review R2):
        # http.server does not URL-decode, so this would otherwise 404 only by chance.
        from sdlc.dashboard.server import resolve_static_file

        static_dir = tmp_path / "static"
        static_dir.mkdir()
        (static_dir / "index.html").write_text("ok", encoding="utf-8")
        assert resolve_static_file("/%2e%2e%2fserver.py", static_dir=static_dir) is None
        assert resolve_static_file("/%2e%2e/", static_dir=static_dir) is None

    @_NEEDS_SYMLINK
    def test_symlink_outside_static_root_returns_none(self, tmp_path: Path) -> None:
        from sdlc.dashboard.server import resolve_static_file

        static_dir = tmp_path / "static"
        static_dir.mkdir()
        (static_dir / "index.html").write_text("ok", encoding="utf-8")
        outside = tmp_path / "secret.txt"
        outside.write_text("secret", encoding="utf-8")
        (static_dir / "escape.txt").symlink_to(outside)
        assert resolve_static_file("/escape.txt", static_dir=static_dir) is None
