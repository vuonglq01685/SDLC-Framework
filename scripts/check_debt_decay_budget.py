"""Debt-decay budget gate (Epic 2A retro action A1, CONTRIBUTING §7.5).

Enforces three gates before Story `N.1` of each epic:

  Gate A (BLOCKING zero-open):
    Every BLOCKING-severity item across the whole budget is closed
    (zero open). Inventory-relative — see ADR-033.

  Gate B (HIGH carry-forward):
    Among HIGH items where ``epic_of_origin != target_epic``, at least
    50% are closed.

  Gate C (N-2 zero-out):
    Items whose ``epic_of_origin`` is two epics back from the target
    must all be closed (zero open).

The budget lives in
``_bmad-output/implementation-artifacts/debt-budget.yaml`` and is the
machine-readable counterpart of ``deferred-work.md``.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import yaml

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
_DEFAULT_BUDGET: Final[Path] = (
    _REPO_ROOT / "_bmad-output" / "implementation-artifacts" / "debt-budget.yaml"
)

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

_HIGH_CARRY_FORWARD_RATIO_NUM: Final[int] = 1
_HIGH_CARRY_FORWARD_RATIO_DEN: Final[int] = 2  # ratio = 1/2 ⇒ ≥50%

_REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "id",
    "severity",
    "status",
    "epic_of_origin",
    "title",
)


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


def _parse_item(index: int, row: object) -> DebtItem:
    if not isinstance(row, dict):
        raise ValueError(f"items[{index}]: must be a mapping, got {type(row).__name__}")
    for field in _REQUIRED_FIELDS:
        if field not in row:
            raise ValueError(f"items[{index}]: missing required field {field!r}")
    sev = row["severity"]
    if sev not in VALID_SEVERITIES:
        raise ValueError(
            f"items[{index}]: unknown severity {sev!r}; expected one of {sorted(VALID_SEVERITIES)}"
        )
    status = row["status"]
    if status not in VALID_STATUSES:
        raise ValueError(
            f"items[{index}]: unknown status {status!r}; expected one of {sorted(VALID_STATUSES)}"
        )
    return DebtItem(
        id=str(row["id"]),
        severity=str(sev),
        status=str(status),
        epic_of_origin=str(row["epic_of_origin"]),
        title=str(row["title"]),
    )


def load_budget(path: Path) -> list[DebtItem]:
    """Parse debt-budget.yaml into DebtItem list. Raise on malformed input."""
    if not path.exists():
        raise FileNotFoundError(f"debt budget not found: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"malformed YAML in {path}: {exc}") from exc

    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError(f"top-level must be a mapping, got {type(raw).__name__}")

    items_raw = raw.get("items", [])
    if not isinstance(items_raw, list):
        raise ValueError(f"'items' must be a list, got {type(items_raw).__name__}")

    return [_parse_item(i, row) for i, row in enumerate(items_raw)]


def resolve_lineage(target_epic: str) -> tuple[str, str]:
    """Return ``(previous, two_back)`` keys for the target epic."""
    if target_epic not in EPIC_LINEAGE:
        raise ValueError(
            f"unknown target epic for lineage: {target_epic!r}; known: {sorted(EPIC_LINEAGE)}"
        )
    return EPIC_LINEAGE[target_epic]


def evaluate_gates(items: list[DebtItem], target_epic: str) -> BudgetReport:
    """Apply the three policy gates and return a structured report."""
    target_key = f"epic-{target_epic}"
    _previous, two_back = resolve_lineage(target_epic)
    two_back_key = f"epic-{two_back}" if two_back else ""

    # Gate A — BLOCKING zero-open: every BLOCKING item closed (ADR-033).
    blocking_open = sum(1 for it in items if it.severity == "BLOCKING" and it.status == "open")
    gate_a = GateResult(
        name="Gate A (BLOCKING zero-open)",
        passed=blocking_open == 0,
        observed=f"{blocking_open} open",
        threshold="0 open",
    )

    # Gate B — HIGH carry-forward (≥50% of non-target HIGH items closed).
    high_cf = [it for it in items if it.severity == "HIGH" and it.epic_of_origin != target_key]
    high_cf_closed = sum(1 for it in high_cf if it.status == "closed")
    total_cf = len(high_cf)
    if total_cf == 0:
        gate_b_pass = True
        observed_b = "n/a (no HIGH carry-forward)"
    else:
        # Integer-safe ≥ratio comparison: closed/total ≥ num/den
        # rearranges to closed*den ≥ total*num.
        gate_b_pass = (
            high_cf_closed * _HIGH_CARRY_FORWARD_RATIO_DEN
            >= total_cf * _HIGH_CARRY_FORWARD_RATIO_NUM
        )
        observed_b = f"{high_cf_closed}/{total_cf} closed"
    gate_b = GateResult(
        name="Gate B (HIGH carry-forward)",
        passed=gate_b_pass,
        observed=observed_b,
        threshold="≥50%",
    )

    # Gate C — N-2 zero-out (no open items from two epics back).
    if not two_back_key:
        gate_c_pass = True
        n2_open = 0
    else:
        n2_open = sum(
            1 for it in items if it.epic_of_origin == two_back_key and it.status == "open"
        )
        gate_c_pass = n2_open == 0
    gate_c = GateResult(
        name="Gate C (N-2 zero-out)",
        passed=gate_c_pass,
        observed=f"{n2_open} open",
        threshold="0",
    )

    return BudgetReport(
        target_epic=target_epic,
        gate_a=gate_a,
        gate_b=gate_b,
        gate_c=gate_c,
    )


def format_audit_table(report: BudgetReport) -> str:
    """Markdown audit table suitable for PR descriptions + CI logs."""
    lines: list[str] = []
    lines.append(f"# Debt-Decay Audit — Target Epic {report.target_epic}")
    lines.append("")
    lines.append("| Gate | Status | Observed | Threshold |")
    lines.append("|---|---|---|---|")
    for gate_res in (report.gate_a, report.gate_b, report.gate_c):
        status = "PASS" if gate_res.passed else "FAIL"
        lines.append(f"| {gate_res.name} | {status} | {gate_res.observed} | {gate_res.threshold} |")
    lines.append("")
    overall = "PASS" if report.passed else "FAIL"
    lines.append(f"**Overall:** {overall}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entry. Exit codes: 0 pass/warn, 1 fail+strict, 2 IO/input error."""
    parser = argparse.ArgumentParser(
        description="Check debt-decay budget before Story N.1 (CONTRIBUTING §7.5)."
    )
    parser.add_argument(
        "--target-epic",
        required=True,
        help="Target epic key (e.g. 2b, 3, 4, 5). Must exist in EPIC_LINEAGE.",
    )
    parser.add_argument(
        "--budget",
        type=Path,
        default=_DEFAULT_BUDGET,
        help=f"Path to debt-budget.yaml (default: {_DEFAULT_BUDGET}).",
    )
    parser.add_argument(
        "--mode",
        choices=("strict", "warn"),
        default="warn",
        help="strict: exit 1 on budget violation; warn: exit 0 with banner (default).",
    )
    args = parser.parse_args(argv)

    try:
        items = load_budget(args.budget)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"ERROR: invalid budget: {exc}", file=sys.stderr)
        return 2

    try:
        report = evaluate_gates(items, args.target_epic)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(format_audit_table(report))

    if report.passed:
        return 0
    if args.mode == "strict":
        return 1
    return 0  # warn-mode = non-blocking by design


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
