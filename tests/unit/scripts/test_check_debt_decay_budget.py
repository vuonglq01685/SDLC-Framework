"""Unit tests for scripts/check_debt_decay_budget.py (C6 / Epic 2A retro A1).

RED phase per CONTRIBUTING.md §2 — tests describe the public surface and
fail until C6 GREEN implements it. Three policy gates are exercised at
their boundaries so a future shift in any threshold (e.g. BLOCKING from
≥5 → ≥7) is caught by a focused regression rather than silent drift.
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

import check_debt_decay_budget as gate

_FIVE_BLOCKING_CLOSED_BUDGET = """\
items:
  - id: B1
    severity: BLOCKING
    status: closed
    epic_of_origin: epic-1
    title: closed blocking 1
  - id: B2
    severity: BLOCKING
    status: closed
    epic_of_origin: epic-1
    title: closed blocking 2
  - id: B3
    severity: BLOCKING
    status: closed
    epic_of_origin: epic-2a
    title: closed blocking 3
  - id: B4
    severity: BLOCKING
    status: closed
    epic_of_origin: epic-2a
    title: closed blocking 4
  - id: B5
    severity: BLOCKING
    status: closed
    epic_of_origin: epic-2a
    title: closed blocking 5
"""


def _write_budget(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "debt-budget.yaml"
    path.write_text(body, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# load_budget
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadBudget:
    def test_loads_well_formed_yaml(self, tmp_path: Path) -> None:
        path = _write_budget(tmp_path, _FIVE_BLOCKING_CLOSED_BUDGET)
        items = gate.load_budget(path)
        assert len(items) == 5
        assert items[0].id == "B1"
        assert items[0].severity == "BLOCKING"
        assert items[0].status == "closed"
        assert items[0].epic_of_origin == "epic-1"
        assert items[0].title == "closed blocking 1"

    def test_missing_file_raises_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            gate.load_budget(tmp_path / "nope.yaml")

    def test_malformed_yaml_raises_value_error(self, tmp_path: Path) -> None:
        # ``items:`` must be a list; a scalar is a structural error.
        path = _write_budget(tmp_path, "items: not-a-list\n")
        with pytest.raises(ValueError):
            gate.load_budget(path)

    def test_unknown_severity_raises_value_error(self, tmp_path: Path) -> None:
        path = _write_budget(
            tmp_path,
            "items:\n"
            "  - id: X1\n"
            "    severity: URGENT\n"  # not in VALID_SEVERITIES
            "    status: open\n"
            "    epic_of_origin: epic-1\n"
            "    title: bad sev\n",
        )
        with pytest.raises(ValueError, match="severity"):
            gate.load_budget(path)

    def test_unknown_status_raises_value_error(self, tmp_path: Path) -> None:
        path = _write_budget(
            tmp_path,
            "items:\n"
            "  - id: X1\n"
            "    severity: HIGH\n"
            "    status: pending\n"  # not in VALID_STATUSES
            "    epic_of_origin: epic-1\n"
            "    title: bad status\n",
        )
        with pytest.raises(ValueError, match="status"):
            gate.load_budget(path)

    def test_missing_required_field_raises_value_error(self, tmp_path: Path) -> None:
        path = _write_budget(
            tmp_path,
            "items:\n"
            "  - id: X1\n"
            "    severity: HIGH\n"
            "    status: open\n"
            # epic_of_origin missing
            "    title: incomplete\n",
        )
        with pytest.raises(ValueError, match="epic_of_origin"):
            gate.load_budget(path)


# ---------------------------------------------------------------------------
# resolve_lineage
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResolveLineage:
    def test_epic_2b_previous_is_2a_two_back_is_1(self) -> None:
        assert gate.resolve_lineage("2b") == ("2a", "1")

    def test_epic_3_previous_is_2b_two_back_is_2a(self) -> None:
        assert gate.resolve_lineage("3") == ("2b", "2a")

    def test_unknown_target_epic_raises(self) -> None:
        with pytest.raises(ValueError, match="lineage"):
            gate.resolve_lineage("99")

    def test_epic_2a_has_no_two_back(self) -> None:
        # Epic 2A is the second epic; "two-back" is the empty sentinel.
        previous, two_back = gate.resolve_lineage("2a")
        assert previous == "1"
        assert two_back == ""


# ---------------------------------------------------------------------------
# evaluate_gates — Gate A (BLOCKING absolute)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGateA:
    def test_empty_budget_fails_gate_a(self) -> None:
        # No BLOCKING closed at all → gate A fails (threshold is ≥5).
        report = gate.evaluate_gates([], target_epic="2b")
        assert report.gate_a.passed is False

    def test_exactly_five_blocking_closed_passes(self, tmp_path: Path) -> None:
        items = gate.load_budget(_write_budget(tmp_path, _FIVE_BLOCKING_CLOSED_BUDGET))
        report = gate.evaluate_gates(items, target_epic="2b")
        assert report.gate_a.passed is True

    def test_four_blocking_closed_fails(self) -> None:
        items = [gate.DebtItem(f"B{i}", "BLOCKING", "closed", "epic-2a", "t") for i in range(4)]
        report = gate.evaluate_gates(items, target_epic="2b")
        assert report.gate_a.passed is False

    def test_open_blocking_does_not_count(self) -> None:
        items = [
            *(gate.DebtItem(f"O{i}", "BLOCKING", "open", "epic-2a", "t") for i in range(10)),
            *(gate.DebtItem(f"C{i}", "BLOCKING", "closed", "epic-2a", "t") for i in range(4)),
        ]
        report = gate.evaluate_gates(items, target_epic="2b")
        assert report.gate_a.passed is False  # only 4 closed, 10 open ignored


# ---------------------------------------------------------------------------
# evaluate_gates — Gate B (HIGH carry-forward ≥50%)
# ---------------------------------------------------------------------------


def _gate_b_baseline_items() -> list[gate.DebtItem]:
    """Five BLOCKING closed so gate A is satisfied; gate B is the focus."""
    return [gate.DebtItem(f"B{i}", "BLOCKING", "closed", "epic-1", "t") for i in range(5)]


@pytest.mark.unit
class TestGateB:
    def test_no_high_carry_forward_passes_trivially(self) -> None:
        items = _gate_b_baseline_items()
        report = gate.evaluate_gates(items, target_epic="2b")
        assert report.gate_b.passed is True

    def test_high_target_epic_not_carry_forward(self) -> None:
        items = [
            *_gate_b_baseline_items(),
            # HIGH items from the TARGET epic (2b) are NOT carry-forward and
            # never affect gate B regardless of status.
            gate.DebtItem("H1", "HIGH", "open", "epic-2b", "t"),
            gate.DebtItem("H2", "HIGH", "open", "epic-2b", "t"),
        ]
        report = gate.evaluate_gates(items, target_epic="2b")
        assert report.gate_b.passed is True

    def test_high_carry_forward_50pct_closed_passes_boundary(self) -> None:
        items = [
            *_gate_b_baseline_items(),
            gate.DebtItem("H1", "HIGH", "closed", "epic-2a", "t"),
            gate.DebtItem("H2", "HIGH", "open", "epic-2a", "t"),
        ]
        report = gate.evaluate_gates(items, target_epic="2b")
        assert report.gate_b.passed is True  # 1/2 = 50%

    def test_high_carry_forward_below_50pct_fails(self) -> None:
        items = [
            *_gate_b_baseline_items(),
            gate.DebtItem("H1", "HIGH", "closed", "epic-2a", "t"),
            gate.DebtItem("H2", "HIGH", "open", "epic-2a", "t"),
            gate.DebtItem("H3", "HIGH", "open", "epic-2a", "t"),
        ]
        report = gate.evaluate_gates(items, target_epic="2b")
        assert report.gate_b.passed is False  # 1/3 ≈ 33%

    def test_gate_b_aggregates_all_carry_forward_epics(self) -> None:
        # Carry-forward = ANY non-target epic of origin (per retro wording
        # "≥50% HIGH carry-forward debt" — not scoped to N-1 alone).
        items = [
            *_gate_b_baseline_items(),
            gate.DebtItem("H1", "HIGH", "closed", "epic-1", "t"),
            gate.DebtItem("H2", "HIGH", "closed", "epic-2a", "t"),
            gate.DebtItem("H3", "HIGH", "open", "epic-2a", "t"),
        ]
        report = gate.evaluate_gates(items, target_epic="2b")
        assert report.gate_b.passed is True  # 2/3 ≈ 67%


# ---------------------------------------------------------------------------
# evaluate_gates — Gate C (N-2 zero-out)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGateC:
    def test_no_n_minus_2_items_passes_trivially(self) -> None:
        items = _gate_b_baseline_items()  # epic-1 IS N-2 for target 2b
        # All five are CLOSED, so gate C still passes.
        report = gate.evaluate_gates(items, target_epic="2b")
        assert report.gate_c.passed is True

    def test_one_open_n_minus_2_item_fails(self) -> None:
        items = [
            *_gate_b_baseline_items(),
            # epic-1 is two-back from target 2b; any open item fails gate C.
            gate.DebtItem("LO1", "LOW", "open", "epic-1", "t"),
        ]
        report = gate.evaluate_gates(items, target_epic="2b")
        assert report.gate_c.passed is False

    def test_gate_c_ignores_n_minus_1_open_items(self) -> None:
        items = [
            *_gate_b_baseline_items(),
            # epic-2a is N-1, not N-2 — open is fine for gate C.
            gate.DebtItem("LO1", "LOW", "open", "epic-2a", "t"),
        ]
        report = gate.evaluate_gates(items, target_epic="2b")
        assert report.gate_c.passed is True

    def test_gate_c_ignores_target_epic_open_items(self) -> None:
        items = [
            *_gate_b_baseline_items(),
            gate.DebtItem("LO1", "LOW", "open", "epic-2b", "t"),
        ]
        report = gate.evaluate_gates(items, target_epic="2b")
        assert report.gate_c.passed is True

    def test_gate_c_severity_independent(self) -> None:
        # Any severity from N-2 with status=open fails gate C.
        for sev in ("BLOCKING", "HIGH", "MED", "LOW"):
            items = [
                *_gate_b_baseline_items(),
                gate.DebtItem("X", sev, "open", "epic-1", "t"),
            ]
            report = gate.evaluate_gates(items, target_epic="2b")
            assert report.gate_c.passed is False, f"severity={sev} should fail gate C"


# ---------------------------------------------------------------------------
# evaluate_gates — overall pass requires all three
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestOverallPass:
    def test_all_three_gates_pass_overall_pass(self, tmp_path: Path) -> None:
        items = gate.load_budget(_write_budget(tmp_path, _FIVE_BLOCKING_CLOSED_BUDGET))
        report = gate.evaluate_gates(items, target_epic="2b")
        assert report.passed is True

    def test_gate_c_fail_blocks_overall_pass(self) -> None:
        items = [
            *_gate_b_baseline_items(),
            gate.DebtItem("X", "LOW", "open", "epic-1", "t"),  # fails gate C
        ]
        report = gate.evaluate_gates(items, target_epic="2b")
        assert report.passed is False
        assert report.gate_a.passed is True
        assert report.gate_b.passed is True
        assert report.gate_c.passed is False


# ---------------------------------------------------------------------------
# format_audit_table
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFormatAuditTable:
    def test_table_includes_target_epic(self) -> None:
        report = gate.evaluate_gates(_gate_b_baseline_items(), target_epic="2b")
        rendered = gate.format_audit_table(report)
        assert "2b" in rendered

    def test_table_lists_each_gate_with_pass_or_fail(self) -> None:
        report = gate.evaluate_gates(_gate_b_baseline_items(), target_epic="2b")
        rendered = gate.format_audit_table(report)
        for name in ("Gate A", "Gate B", "Gate C"):
            assert name in rendered
        assert "PASS" in rendered or "FAIL" in rendered

    def test_table_shows_observed_versus_threshold(self) -> None:
        report = gate.evaluate_gates(_gate_b_baseline_items(), target_epic="2b")
        rendered = gate.format_audit_table(report)
        # Each gate row carries both the observed value and the threshold.
        assert report.gate_a.observed in rendered
        assert report.gate_a.threshold in rendered


# ---------------------------------------------------------------------------
# main — CLI exit codes
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMainCli:
    def test_passing_budget_strict_exit_0(self, tmp_path: Path) -> None:
        path = _write_budget(tmp_path, _FIVE_BLOCKING_CLOSED_BUDGET)
        rc = gate.main(["--target-epic", "2b", "--budget", str(path), "--mode", "strict"])
        assert rc == 0

    def test_failing_budget_strict_exit_1(self, tmp_path: Path) -> None:
        # Empty budget — gate A fails immediately.
        path = _write_budget(tmp_path, "items: []\n")
        rc = gate.main(["--target-epic", "2b", "--budget", str(path), "--mode", "strict"])
        assert rc == 1

    def test_failing_budget_warn_exit_0(self, tmp_path: Path) -> None:
        path = _write_budget(tmp_path, "items: []\n")
        rc = gate.main(["--target-epic", "2b", "--budget", str(path), "--mode", "warn"])
        assert rc == 0

    def test_missing_budget_file_exit_2(self, tmp_path: Path) -> None:
        rc = gate.main(
            ["--target-epic", "2b", "--budget", str(tmp_path / "nope.yaml"), "--mode", "strict"]
        )
        assert rc == 2

    def test_unknown_target_epic_exit_2(self, tmp_path: Path) -> None:
        path = _write_budget(tmp_path, _FIVE_BLOCKING_CLOSED_BUDGET)
        rc = gate.main(["--target-epic", "99", "--budget", str(path), "--mode", "strict"])
        assert rc == 2


# ---------------------------------------------------------------------------
# Anti-tautology receipt (per ADR-026 §1)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAntiTautologyReceipt:
    def test_passing_assertion_is_load_bearing(self, tmp_path: Path) -> None:
        """Neutralise ``evaluate_gates`` to a forced-fail and confirm the
        passing-budget CLI test would in fact fail. If this neutralised
        run still reports rc=0, the strict-mode pass assertion is a
        tautology and must be tightened.
        """
        path = _write_budget(tmp_path, _FIVE_BLOCKING_CLOSED_BUDGET)
        forced_fail = gate.BudgetReport(
            target_epic="2b",
            gate_a=gate.GateResult("Gate A", False, "0", "≥5"),
            gate_b=gate.GateResult("Gate B", False, "0/0", "≥50%"),
            gate_c=gate.GateResult("Gate C", False, "1", "0"),
        )
        with mock.patch.object(gate, "evaluate_gates", return_value=forced_fail):
            rc = gate.main(["--target-epic", "2b", "--budget", str(path), "--mode", "strict"])
        assert rc == 1, (
            "evaluate_gates is not actually consulted by main(); pass test is a tautology"
        )
