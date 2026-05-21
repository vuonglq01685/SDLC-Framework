"""Debt-decay budget gate (Epic 2A retro action A1, CONTRIBUTING §7.5).

Enforces three gates before Story `N.1` of each epic:

  Gate A (BLOCKING absolute):
    ≥5 BLOCKING items currently closed across the whole budget.

  Gate B (HIGH carry-forward):
    Among HIGH items where ``epic_of_origin != target_epic``, at least
    50% are closed.

  Gate C (N-2 zero-out):
    Items whose ``epic_of_origin`` is two epics back from the target
    must all be closed (zero open).

The budget lives in
``_bmad-output/implementation-artifacts/debt-budget.yaml`` and is the
machine-readable counterpart of ``deferred-work.md``.

Skeleton only — implementation lands in C6 GREEN step.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]

# Epic lineage ordering. ``target -> (previous, two_back)``. Extend as new
# epics land. Underscore-free strings (e.g. ``"2a"``, not ``"2-a"``) match
# the keys used throughout sprint-status.yaml.
EPIC_LINEAGE: Final[dict[str, tuple[str, str]]] = {
    "2a": ("1", ""),
    "2b": ("2a", "1"),
    "3": ("2b", "2a"),
    "4": ("3", "2b"),
    "5": ("4", "3"),
}

VALID_SEVERITIES: Final[frozenset[str]] = frozenset({"BLOCKING", "HIGH", "MED", "LOW"})
VALID_STATUSES: Final[frozenset[str]] = frozenset({"open", "closed"})


@dataclass(frozen=True)
class DebtItem:
    """One row in debt-budget.yaml."""

    id: str
    severity: str
    status: str
    epic_of_origin: str
    title: str


@dataclass(frozen=True)
class GateResult:
    name: str
    passed: bool
    observed: str
    threshold: str


@dataclass(frozen=True)
class BudgetReport:
    target_epic: str
    gate_a: GateResult
    gate_b: GateResult
    gate_c: GateResult

    @property
    def passed(self) -> bool:
        return self.gate_a.passed and self.gate_b.passed and self.gate_c.passed


def load_budget(path: Path) -> list[DebtItem]:
    """Parse debt-budget.yaml into DebtItem list. Raise on malformed input."""
    raise NotImplementedError("C6 GREEN")


def resolve_lineage(target_epic: str) -> tuple[str, str]:
    """Return ``(previous, two_back)`` keys for the target epic."""
    raise NotImplementedError("C6 GREEN")


def evaluate_gates(items: list[DebtItem], target_epic: str) -> BudgetReport:
    """Apply the three policy gates and return a structured report."""
    raise NotImplementedError("C6 GREEN")


def format_audit_table(report: BudgetReport) -> str:
    """Markdown audit table suitable for PR descriptions + CI logs."""
    raise NotImplementedError("C6 GREEN")


def main(argv: list[str] | None = None) -> int:
    """CLI entry. Exit codes: 0 pass/warn, 1 fail+strict, 2 IO/input error."""
    raise NotImplementedError("C6 GREEN")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
