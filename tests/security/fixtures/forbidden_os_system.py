"""Anti-tautology fixture for the AC2/D2 ``os.system`` forbidden-call branch.

Post-review patch P25: the AC2 forbidden-list (``os.system`` / ``os.popen`` /
``os.spawn*``) had no load-bearing receipt before this fixture. The
accompanying test in tests/security/test_subprocess_allowlist.py asserts the
scanner flags this fixture with ``binary='os.system'`` and reason ``os
shell/process APIs are forbidden``.
"""

from __future__ import annotations

import os  # noqa: net -- anti-tautology fixture; os.system below is the test target


def _bad() -> int:
    return os.system("ls /tmp")
