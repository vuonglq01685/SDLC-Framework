"""Local dashboard HTTP server (Story 5.1).

Threat model (NFR-SEC-6): the dashboard binds ``127.0.0.1`` only, requires no
authentication, and assumes the **local user is trusted**. It is a read-only
surface exposing project state and metrics to the operator's browser on the same
machine. Remote access is intentionally unsupported in v1. DNS-rebinding is
mitigated via a ``Host``-header allowlist (see ``server.validate_host_header``).
"""

from __future__ import annotations
