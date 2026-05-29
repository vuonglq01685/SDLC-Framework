"""Anti-tautology fixture for the AC2 ``<dynamic>`` allow-list sentinel.

Post-review patch P24: the AC2 negative case (forbidden_subprocess.py) proves
the scanner can flag a binary not on the allow-list, but the POSITIVE case for
the ``<dynamic>`` sentinel (modules legitimately invoking a per-call binary
like ``src/sdlc/hooks/runner.py``) had no load-bearing receipt before this
fixture. The accompanying test in tests/security/test_subprocess_allowlist.py
monkey-patches the allow-list to include this fixture's path with the
``<dynamic>`` sentinel and asserts ZERO violations.
"""

from __future__ import annotations

import subprocess  # noqa: subprocess -- anti-tautology fixture for AC2/D3 <dynamic>


def _invoke(binary_name: str) -> int:
    # Dynamic binary name resolved at call time (mirrors hooks/runner.py
    # per-hook indirection — the binary value is loaded from a registry).
    return subprocess.run([binary_name, "--help"], check=False).returncode
