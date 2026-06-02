"""MODULE_DEPS + SPECIFIC_RULE_MAP for check_module_boundaries.py (ADR-010).

Split from the validator script to keep scripts/check_module_boundaries.py under
the Architecture §765 LOC cap while the dependency table grows.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModuleSpec:
    depends_on: frozenset[str]
    forbidden_from: frozenset[str]


MODULE_DEPS: dict[str, ModuleSpec] = {
    "errors": ModuleSpec(
        depends_on=frozenset(),
        forbidden_from=frozenset(),
    ),
    "ids": ModuleSpec(
        depends_on=frozenset({"errors"}),
        forbidden_from=frozenset(),
    ),
    "contracts": ModuleSpec(
        depends_on=frozenset({"errors", "ids"}),
        forbidden_from=frozenset({"engine", "dispatcher", "cli"}),
    ),
    "config": ModuleSpec(
        depends_on=frozenset({"errors", "contracts"}),
        forbidden_from=frozenset({"engine", "dispatcher", "cli"}),
    ),
    "concurrency": ModuleSpec(
        depends_on=frozenset({"errors"}),
        forbidden_from=frozenset({"engine", "state", "journal"}),
    ),
    "state": ModuleSpec(
        depends_on=frozenset({"errors", "contracts", "concurrency", "config", "journal"}),
        forbidden_from=frozenset({"engine", "dispatcher", "runtime", "cli"}),
    ),
    "journal": ModuleSpec(
        depends_on=frozenset({"errors", "contracts", "concurrency", "config"}),
        forbidden_from=frozenset({"engine", "dispatcher", "runtime", "cli"}),
    ),
    "signoff": ModuleSpec(
        # concurrency: per-phase flock for write_record/invalidate_record
        # (EPIC-2A-D7A / ADR-034). state + journal already depend on it.
        depends_on=frozenset({"errors", "contracts", "state", "journal", "concurrency"}),
        forbidden_from=frozenset({"engine", "dispatcher", "cli"}),
    ),
    "runtime": ModuleSpec(
        depends_on=frozenset({"errors", "contracts", "concurrency"}),
        forbidden_from=frozenset({"engine", "dispatcher", "state", "journal", "cli"}),
    ),
    "workflows": ModuleSpec(
        depends_on=frozenset({"errors", "contracts", "ids"}),
        forbidden_from=frozenset({"engine", "dispatcher", "runtime"}),
    ),
    "workflows_yaml": ModuleSpec(
        depends_on=frozenset({"errors"}),
        forbidden_from=frozenset({"engine", "dispatcher", "runtime", "cli"}),
    ),
    "specialists": ModuleSpec(
        depends_on=frozenset({"errors", "contracts", "workflows"}),
        forbidden_from=frozenset({"engine", "dispatcher", "runtime"}),
    ),
    "hooks": ModuleSpec(
        depends_on=frozenset({"errors", "contracts", "state", "journal", "ids"}),
        forbidden_from=frozenset({"engine", "dispatcher", "runtime", "cli"}),
    ),
    "telemetry": ModuleSpec(
        depends_on=frozenset({"errors", "contracts", "journal", "concurrency"}),
        forbidden_from=frozenset({"engine", "dispatcher", "runtime", "cli"}),
    ),
    "dispatcher": ModuleSpec(
        depends_on=frozenset(
            {
                "errors",
                "runtime",
                "workflows",
                "specialists",
                "state",
                "journal",
                "hooks",
                "telemetry",
                "concurrency",
                "config",
                "contracts",
                "ids",
                "signoff",
            }
        ),
        forbidden_from=frozenset({"engine", "cli"}),
    ),
    "engine": ModuleSpec(
        depends_on=frozenset(
            {
                "errors",
                "ids",
                "state",
                "journal",
                "signoff",
                "dispatcher",
                "hooks",
                "telemetry",
                "workflows",
                "specialists",
                "runtime",
                "config",
            }
        ),
        forbidden_from=frozenset({"cli", "dashboard"}),
    ),
    "adopt": ModuleSpec(
        # Story 3.1: the ratified seed omitted the foundation modules the driver provably
        # needs — `contracts` (build JournalEntry/AdoptReport), `concurrency` (atomic
        # adopt-report.json write), `ids` (RFC-3339 timestamp). Added as a corrective
        # amendment (NOT a re-creation); the architecture.md:1069 MAY/MUST-NOT lists were
        # silent on these foundation deps. forbidden_from unchanged (Architecture Rule 6).
        depends_on=frozenset(
            {
                "errors",
                "contracts",
                "ids",
                "concurrency",
                "state",
                "journal",
                "signoff",
                "config",
            }
        ),
        forbidden_from=frozenset({"engine", "dispatcher", "runtime"}),
    ),
    "migrations": ModuleSpec(
        depends_on=frozenset({"errors", "state"}),
        forbidden_from=frozenset({"engine", "dispatcher", "runtime", "cli"}),
    ),
    "dashboard": ModuleSpec(
        depends_on=frozenset({"errors", "state", "journal", "telemetry", "signoff", "config"}),
        forbidden_from=frozenset({"engine", "dispatcher", "runtime", "hooks", "adopt"}),
    ),
    "cli": ModuleSpec(
        depends_on=frozenset(
            {
                "engine",
                "adopt",
                "dashboard",
                "runtime",
                "config",
                "errors",
                "state",
                "journal",
                "contracts",
                "ids",
                "migrations",
                "hooks",
                "concurrency",
                "dispatcher",
                "specialists",
                "workflows",
                "workflows_yaml",
                "signoff",
            }
        ),
        forbidden_from=frozenset(),
    ),
    "agents": ModuleSpec(
        depends_on=frozenset({"errors", "contracts", "workflows", "specialists"}),
        forbidden_from=frozenset({"engine", "dispatcher", "runtime", "cli", "state", "journal"}),
    ),
    "claude_hooks": ModuleSpec(
        depends_on=frozenset(),
        forbidden_from=frozenset(
            {"engine", "dispatcher", "runtime", "state", "journal", "hooks", "cli"}
        ),
    ),
}


SPECIFIC_RULE_MAP: dict[tuple[str, str], int] = {
    ("engine", "dashboard"): 4,
    ("hooks", "engine"): 5,
    ("hooks", "dispatcher"): 5,
    ("adopt", "engine"): 6,
    ("adopt", "dispatcher"): 6,
    ("workflows", "engine"): 7,
    ("workflows", "dispatcher"): 7,
    ("workflows", "runtime"): 7,
    ("specialists", "engine"): 7,
    ("specialists", "dispatcher"): 7,
    ("specialists", "runtime"): 7,
}


def _validate_module_deps_table() -> None:
    """Module-level invariant: every value in any depends_on / forbidden_from is a
    declared MODULE_DEPS key. Catches typos at import time, not at runtime."""
    known = frozenset(MODULE_DEPS)
    for name, spec in MODULE_DEPS.items():
        unknown = (spec.depends_on | spec.forbidden_from) - known
        if unknown:
            raise AssertionError(
                f"MODULE_DEPS[{name!r}] references unknown module(s): {sorted(unknown)}"
            )


_validate_module_deps_table()
