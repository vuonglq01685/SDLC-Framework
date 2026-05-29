"""Anti-tautology fixture for the AC1 ``# noqa: net -- <reason>`` exemption path.

Post-review patch P23: the AC1 negative case (forbidden_net_import.py) proves
the scanner can flag a violation, but the POSITIVE case (exemption marker
correctly suppresses the flag) had no load-bearing receipt before this fixture.
"""

from __future__ import annotations

import requests  # noqa: net -- legacy CI integration retained for compatibility shim

_USED = requests
