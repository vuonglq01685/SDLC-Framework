#!/usr/bin/env python3
"""Run mutmut on ``src/sdlc/adopt/`` and enforce >=95% kill rate (Story 3.7, AC2)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_MIN_KILL_RATE = 0.95
_REPO_ROOT = Path(__file__).resolve().parent.parent
# Invoke the mutmut console script, NOT `python -m mutmut`: under `-m`, mutmut/__main__.py runs as
# `__main__`, and the trampoline mutmut injects into every mutated module re-imports it as
# `mutmut.__main__` (a distinct module object), re-running its top-level `set_start_method("fork")`
# -> RuntimeError("context has already been set"), aborting stats collection. The console script
# imports __main__ once under its canonical name, so the trampoline's import is cached.
_MUTMUT = str(Path(sys.executable).parent / "mutmut")


def _run(cmd: list[str], *, check: bool = True) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=_REPO_ROOT, check=check)


def main() -> int:
    _run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/unit/adopt/",
            "tests/property/test_source_untouched_invariant.py",
            "tests/property/test_source_untouched_adversarial.py",
            "tests/property/test_source_untouched_submodule.py",
            "tests/property/test_source_untouched_stateful.py",
            "tests/integration/test_adopt_mode_invariant.py",
            "-q",
            "--no-cov",
        ]
    )
    # mutmut 3.x reads `paths_to_mutate` from `[tool.mutmut]` (pyproject.toml); `run` has no
    # `--paths-to-mutate` flag and `export-cicd-stats` takes no path argument — it writes a
    # hardcoded location under `mutants/`.
    # `mutmut run` exits non-zero when mutants survive; that is not a harness failure, so do
    # not let `check=True` abort here — the kill-rate computation below (guarded by is_file()
    # and total == 0) is the authoritative >=95% gate.
    _run([_MUTMUT, "run"], check=False)
    _run([_MUTMUT, "export-cicd-stats"])
    stats_path = _REPO_ROOT / "mutants" / "mutmut-cicd-stats.json"
    if not stats_path.is_file():
        print(
            f"mutmut produced no stats at {stats_path}; cannot compute kill rate", file=sys.stderr
        )
        return 1
    try:
        stats = json.loads(stats_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        print(f"mutmut stats at {stats_path} are unreadable or malformed: {exc}", file=sys.stderr)
        return 1
    killed = int(stats.get("killed") or 0)
    total = int(stats.get("total") or 0) or sum(
        int(stats.get(key) or 0)
        for key in ("killed", "survived", "timeout", "suspicious", "no_tests", "skipped")
    )
    if total == 0:
        print("mutmut reported zero mutations — cannot compute kill rate", file=sys.stderr)
        return 1
    no_tests = int(stats.get("no_tests") or 0)
    if no_tests == total:
        print(
            f"mutmut: all {total} mutants had no_tests — harness is broken "
            "(check pytest collection, also_copy config, and --no-cov flag)",
            file=sys.stderr,
        )
        return 1
    rate = killed / total
    print(f"adopt mutation kill rate: {killed}/{total} = {rate:.2%}")
    if rate < _MIN_KILL_RATE:
        print(f"FAIL: kill rate {rate:.2%} < {_MIN_KILL_RATE:.0%}", file=sys.stderr)
        return 1
    print(f"PASS: kill rate >= {_MIN_KILL_RATE:.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
