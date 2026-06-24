"""Dashboard HTTP server — stdlib ``http.server``, localhost-only (Story 5.1)."""

from __future__ import annotations

import mimetypes
import socket
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar, Final, cast

from sdlc.concurrency.path_guard import assert_contained
from sdlc.dashboard.router import RequestContext, Response, Router
from sdlc.dashboard.routes.dora import register_dora_route
from sdlc.dashboard.routes.state import register_state_route
from sdlc.errors import SecurityError

_BIND_FORBIDDEN_MESSAGE: Final[str] = (
    "dashboard must bind localhost only; remote access not supported in v1"
)
_LOCALHOST_BIND: Final[str] = "127.0.0.1"
_ALLOWED_HOSTS: Final[frozenset[str]] = frozenset({"localhost", "127.0.0.1", "::1"})
_ALLOWED_BIND_HOSTS: Final[frozenset[str]] = frozenset({"127.0.0.1", "::1", "localhost"})
_READ_METHODS: Final[frozenset[str]] = frozenset({"GET", "HEAD"})
_IMMUTABLE_CACHE: Final[str] = "public, max-age=31536000, immutable"
_STATIC_URL_PREFIX: Final[str] = "static/"


def _register_font_mime_types() -> None:
    """Register font MIME types absent from stdlib mimetypes on Python 3.10-3.13."""
    mimetypes.add_type("font/woff2", ".woff2")
    mimetypes.add_type("font/woff", ".woff")


_register_font_mime_types()


def static_root() -> Path:
    return Path(__file__).resolve().parent / "static"


def validate_bind_host(host: str) -> None:
    """Reject non-localhost bind addresses at startup (AC1).

    Allowlist, not a denylist (CR5.1 review R3): rejecting only the literal string
    ``0.0.0.0`` would still let ``::``, ``""``, LAN IPs, or hostnames bind a remotely
    reachable socket. Only loopback binds are permitted.
    """
    if host not in _ALLOWED_BIND_HOSTS:
        raise SecurityError(_BIND_FORBIDDEN_MESSAGE)


def _parse_host_header(host_header: str) -> tuple[str, int | None]:  # noqa: PLR0911
    """Return (host, port_or_none) from an HTTP Host header value."""
    if host_header.startswith("["):
        end = host_header.find("]")
        if end == -1:
            return host_header, None
        host = host_header[1:end]
        rest = host_header[end + 1 :]
        if rest.startswith(":"):
            try:
                return host, int(rest[1:])
            except ValueError:
                return host, None
        return host, None
    if ":" in host_header:
        host, _, port_str = host_header.rpartition(":")
        try:
            return host, int(port_str)
        except ValueError:
            return host_header, None
    return host_header, None


def validate_host_header(host_header: str | None, *, port: int) -> bool:
    """Return True when ``Host`` is in the localhost allowlist (AC5)."""
    if not host_header:
        return False
    host_only, header_port = _parse_host_header(host_header)
    if host_only.lower() not in _ALLOWED_HOSTS:
        return False
    if header_port is not None:
        return header_port == port
    return True


def build_router(*, repo_root: Path) -> Router:
    router = Router()
    register_state_route(router, repo_root=repo_root)
    register_dora_route(router)
    return router


def resolve_static_file(request_path: str, *, static_dir: Path) -> Path | None:
    """Map a URL path to a file under ``static_dir``, or None when disallowed (AC6)."""
    if "%" in request_path:
        # Reject percent-encoded static paths outright (AC6 explicit traversal defense,
        # CR5.1 review R2): http.server does not URL-decode, so an encoded ``..`` would
        # otherwise slip past the containment guard and 404 only by file-non-existence.
        return None
    rel = request_path.lstrip("/")
    # Decision D1 (Story 5.3): ``/static/…`` maps to the package static root.
    if rel.startswith(_STATIC_URL_PREFIX):
        rel = rel[len(_STATIC_URL_PREFIX) :]
    if rel == "" or rel.endswith("/"):
        rel = "index.html"
    candidate = static_dir / rel
    try:
        return assert_contained(candidate, static_dir)
    except SecurityError:
        return None


def serve_static(request_path: str, *, static_dir: Path) -> Response | None:
    safe = resolve_static_file(request_path, static_dir=static_dir)
    if safe is None or not safe.is_file():
        return None
    content_type, _ = mimetypes.guess_type(str(safe))
    headers: dict[str, str] = {}
    if content_type:
        headers["Content-Type"] = content_type
    if safe.name != "index.html":
        headers["Cache-Control"] = _IMMUTABLE_CACHE
    return Response(status=200, headers=headers, body=safe.read_bytes())


def _write_response(
    handler: BaseHTTPRequestHandler, response: Response, *, head: bool = False
) -> None:
    if response.status >= HTTPStatus.BAD_REQUEST:
        # Close the connection on error short-circuits so an undrained request body
        # cannot desync a keep-alive connection (CR5.1 review R6).
        handler.close_connection = True
    handler.send_response(response.status)
    for key, value in response.headers.items():
        handler.send_header(key, value)
    handler.send_header("Content-Length", str(len(response.body)))
    handler.end_headers()
    if response.body and response.status != HTTPStatus.NOT_MODIFIED and not head:
        handler.wfile.write(response.body)


class DashboardRequestHandler(BaseHTTPRequestHandler):
    """Per-request handler wired to a shared ``Router``."""

    router: ClassVar[Router]
    repo_root: ClassVar[Path]
    static_dir: ClassVar[Path]
    server_port: ClassVar[int]

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _dispatch(self, method: str) -> None:
        # Host-allowlist runs first, for EVERY method (AC5 — applies to all requests,
        # incl. HEAD/OPTIONS/TRACE/CONNECT — CR5.1 review R1).
        if not validate_host_header(self.headers.get("Host"), port=self.server_port):
            _write_response(self, Response(status=403, body=b"Forbidden"))
            return

        # Read-only surface: anything but GET/HEAD (writes, OPTIONS, TRACE, CONNECT, …)
        # is rejected with 405 (AC4).
        if method not in _READ_METHODS:
            _write_response(self, Response(status=405, headers={"Allow": "GET, HEAD"}))
            return

        head = method == "HEAD"
        ctx = RequestContext(
            method="GET",
            path=self.path.split("?", 1)[0],
            headers=dict(self.headers.items()),
            repo_root=self.repo_root,
            static_root=self.static_dir,
        )

        handler = self.router.dispatch(ctx)
        if handler is not None:
            _write_response(self, handler(ctx), head=head)
            return

        static_response = serve_static(ctx.path, static_dir=self.static_dir)
        if static_response is not None:
            _write_response(self, static_response, head=head)
            return

        _write_response(self, Response(status=404, body=b"Not Found"), head=head)

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_HEAD(self) -> None:
        self._dispatch("HEAD")

    def do_OPTIONS(self) -> None:
        self._dispatch("OPTIONS")

    def do_TRACE(self) -> None:
        self._dispatch("TRACE")

    def do_CONNECT(self) -> None:
        self._dispatch("CONNECT")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_PUT(self) -> None:
        self._dispatch("PUT")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")

    def do_PATCH(self) -> None:
        self._dispatch("PATCH")


class DashboardHTTPServer(ThreadingHTTPServer):
    """Threading HTTP server bound to localhost."""


def create_server(
    *,
    repo_root: Path,
    host: str = _LOCALHOST_BIND,
    port: int = 8765,
) -> DashboardHTTPServer:
    validate_bind_host(host)
    router = build_router(repo_root=repo_root)
    static_dir = static_root()

    handler_cls = cast(
        "type[DashboardRequestHandler]",
        type(
            "BoundDashboardHandler",
            (DashboardRequestHandler,),
            {
                "router": router,
                "repo_root": repo_root,
                "static_dir": static_dir,
                "server_port": port,
            },
        ),
    )
    server = DashboardHTTPServer((host, port), handler_cls)
    server.allow_reuse_address = True
    # Reflect the actually-bound port (matters when port=0 → ephemeral) so the Host
    # allowlist compares against the real port, not the requested one (CR5.1 review R4).
    handler_cls.server_port = int(server.server_address[1])
    return server


def serve_dashboard(*, repo_root: Path, host: str = _LOCALHOST_BIND, port: int = 8765) -> None:
    """Block serving the dashboard until interrupted."""
    server = create_server(repo_root=repo_root, host=host, port=port)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def find_free_port() -> int:
    """Return an ephemeral localhost port for tests."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((_LOCALHOST_BIND, 0))
        return int(sock.getsockname()[1])


def serve_dashboard_in_thread(
    *,
    repo_root: Path,
    port: int,
    host: str = _LOCALHOST_BIND,
) -> tuple[DashboardHTTPServer, threading.Thread]:
    """Start the dashboard in a daemon thread (tests)."""
    server = create_server(repo_root=repo_root, host=host, port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread
