"""Anti-tautology fixture: intentionally forbidden subprocess binary."""

from __future__ import annotations

import subprocess


def bad_call() -> None:
    subprocess.run(["arbitrary", "--flag"], check=False)
