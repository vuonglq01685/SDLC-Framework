"""Unit tests for the boundary-validator core logic in scripts/check_module_boundaries.py.

Covers MODULE_DEPS table, file_to_module path mapping, _extract_sdlc_imports
AST extraction, check_imports rule enforcement (including §1103-#N per-rule
citation and TYPE_CHECKING-block skipping). LOC-cap and main() integration
tests live in tests/test_module_boundaries_main.py.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import check_module_boundaries as mb

# ---------------------------------------------------------------------------
# MODULE_DEPS completeness + invariants
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_module_deps_contains_all_17_modules() -> None:
    expected = {
        "errors",
        "ids",
        "contracts",
        "config",
        "concurrency",
        "state",
        "journal",
        "signoff",
        "runtime",
        "workflows",
        "specialists",
        "hooks",
        "telemetry",
        "dispatcher",
        "engine",
        "adopt",
        "dashboard",
        "cli",
        "agents",
    }
    assert set(mb.MODULE_DEPS.keys()) == expected


@pytest.mark.unit
def test_errors_module_has_empty_depends_on() -> None:
    assert mb.MODULE_DEPS["errors"].depends_on == frozenset()


@pytest.mark.unit
def test_errors_module_has_empty_forbidden_from() -> None:
    # errors is enforced via the leaf-module branch in check_imports,
    # not via the forbidden_from set. The set must be empty (no sentinels).
    assert mb.MODULE_DEPS["errors"].forbidden_from == frozenset()


@pytest.mark.unit
def test_cli_has_empty_forbidden_from() -> None:
    assert mb.MODULE_DEPS["cli"].forbidden_from == frozenset()


@pytest.mark.unit
def test_agents_module_present_with_conservative_profile() -> None:
    spec = mb.MODULE_DEPS["agents"]
    assert "errors" in spec.depends_on
    assert "specialists" in spec.depends_on
    # Conservative leaf-of-leaves: forbids the entire upper stack + state/journal.
    for forbidden in ("engine", "dispatcher", "runtime", "cli", "state", "journal"):
        assert forbidden in spec.forbidden_from, f"agents must forbid {forbidden}"


@pytest.mark.unit
def test_module_deps_invariant_no_unknown_references() -> None:
    """Re-run the import-time invariant for visibility (and fail loudly if violated)."""
    mb._validate_module_deps_table()
    known = frozenset(mb.MODULE_DEPS)
    for name, spec in mb.MODULE_DEPS.items():
        assert (spec.depends_on | spec.forbidden_from) <= known, name


# ---------------------------------------------------------------------------
# file_to_module
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_file_to_module_returns_module_for_submodule_file(tmp_path: Path) -> None:
    sdlc_root = tmp_path / "src" / "sdlc"
    state_dir = sdlc_root / "state"
    state_dir.mkdir(parents=True)
    f = state_dir / "atomic.py"
    f.touch()
    assert mb.file_to_module(f, sdlc_root=sdlc_root) == "state"


@pytest.mark.unit
def test_file_to_module_returns_none_for_package_init(tmp_path: Path) -> None:
    sdlc_root = tmp_path / "src" / "sdlc"
    sdlc_root.mkdir(parents=True)
    init = sdlc_root / "__init__.py"
    init.touch()
    assert mb.file_to_module(init, sdlc_root=sdlc_root) is None


@pytest.mark.unit
def test_file_to_module_returns_none_for_tests_file(tmp_path: Path) -> None:
    sdlc_root = tmp_path / "src" / "sdlc"
    sdlc_root.mkdir(parents=True)
    tests_file = tmp_path / "tests" / "test_foo.py"
    tests_file.parent.mkdir()
    tests_file.touch()
    assert mb.file_to_module(tests_file, sdlc_root=sdlc_root) is None


@pytest.mark.unit
def test_file_to_module_returns_none_for_scripts_file(tmp_path: Path) -> None:
    sdlc_root = tmp_path / "src" / "sdlc"
    sdlc_root.mkdir(parents=True)
    script = tmp_path / "scripts" / "check_module_boundaries.py"
    script.parent.mkdir()
    script.touch()
    assert mb.file_to_module(script, sdlc_root=sdlc_root) is None


@pytest.mark.unit
def test_file_to_module_handles_top_level_flat_file(tmp_path: Path) -> None:
    """src/sdlc/version.py -> 'version' (P5: don't silently skip flat-file submodules)."""
    sdlc_root = tmp_path / "src" / "sdlc"
    sdlc_root.mkdir(parents=True)
    flat = sdlc_root / "version.py"
    flat.touch()
    assert mb.file_to_module(flat, sdlc_root=sdlc_root) == "version"


# ---------------------------------------------------------------------------
# _extract_sdlc_imports
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_extract_imports_handles_import_and_from_import() -> None:
    tree = ast.parse(
        "import sdlc\n"
        "import sdlc.engine.auto_loop\n"
        "from sdlc.state import atomic\n"
        "from sdlc.contracts.journal_entry import JournalEntry\n"
        "from os import path  # not an sdlc.* import\n"
    )
    targets = {imp.module for imp in mb._extract_sdlc_imports(tree)}
    assert "sdlc" in targets
    assert "sdlc.engine.auto_loop" in targets
    assert "sdlc.state" in targets
    assert "sdlc.contracts.journal_entry" in targets
    assert "os" not in targets


@pytest.mark.unit
def test_extract_imports_ignores_non_sdlc_modules() -> None:
    tree = ast.parse("from pydantic import BaseModel\nimport os\nimport re\n")
    assert mb._extract_sdlc_imports(tree) == []


@pytest.mark.unit
def test_extract_imports_flags_relative_imports_in_src_module() -> None:
    tree = ast.parse("from . import atomic\nfrom ..engine import auto_loop\n")
    imports = mb._extract_sdlc_imports(tree, src_module="state")
    assert len(imports) == 2
    assert all(imp.module == "<RELATIVE>" for imp in imports)


@pytest.mark.unit
def test_extract_imports_allows_relative_imports_outside_src_module() -> None:
    tree = ast.parse("from . import something\n")
    assert mb._extract_sdlc_imports(tree, src_module=None) == []


@pytest.mark.unit
def test_extract_imports_captures_from_sdlc_submodule_form() -> None:
    """`from sdlc import engine, dispatcher` — each name is a submodule target (P2)."""
    tree = ast.parse("from sdlc import engine, dispatcher\n")
    targets = {imp.module for imp in mb._extract_sdlc_imports(tree)}
    assert targets == {"sdlc.engine", "sdlc.dispatcher"}


@pytest.mark.unit
def test_extract_imports_skips_type_checking_block() -> None:
    """`if TYPE_CHECKING:` imports are type-only, not runtime (P14 / PEP 484)."""
    tree = ast.parse(
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from sdlc.engine import EngineProtocol\n"
        "from sdlc.errors import SdlcError\n"
    )
    targets = {imp.module for imp in mb._extract_sdlc_imports(tree, src_module="state")}
    assert "sdlc.errors" in targets
    assert "sdlc.engine" not in targets


@pytest.mark.unit
def test_extract_imports_skips_typing_dot_type_checking_block() -> None:
    """Also handles `if typing.TYPE_CHECKING:` attribute-form (P14)."""
    tree = ast.parse(
        "import typing\nif typing.TYPE_CHECKING:\n    from sdlc.engine import EngineProtocol\n"
    )
    assert mb._extract_sdlc_imports(tree, src_module="state") == []


# ---------------------------------------------------------------------------
# check_imports — baseline
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_clean_import_within_dependency_table_passes() -> None:
    violations = mb.check_imports(
        "state",
        [
            mb.Import(line=1, module="sdlc.errors"),
            mb.Import(line=2, module="sdlc.contracts.journal_entry"),
        ],
    )
    assert violations == []


@pytest.mark.unit
def test_self_import_is_ignored() -> None:
    violations = mb.check_imports("state", [mb.Import(line=1, module="sdlc.state")])
    assert violations == []


@pytest.mark.unit
def test_bare_sdlc_import_is_ignored() -> None:
    violations = mb.check_imports("state", [mb.Import(line=1, module="sdlc")])
    assert violations == []


@pytest.mark.unit
def test_unknown_module_returns_no_violations() -> None:
    violations = mb.check_imports("typo_module", [mb.Import(line=1, module="sdlc.errors")])
    assert violations == []


# ---------------------------------------------------------------------------
# check_imports — §1103 specific boundary rules (table-driven)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "src_module,target,must_fail",
    [
        ("state", "journal", True),  # §1103-#3: state/journal siblings
        ("journal", "state", True),
        ("dashboard", "engine", True),  # §1103-#4: dashboard read-only
        ("dashboard", "dispatcher", True),
        ("hooks", "engine", True),  # §1103-#5
        ("hooks", "dispatcher", True),
        ("adopt", "engine", True),  # §1103-#6
        ("adopt", "dispatcher", True),
        ("workflows", "engine", True),  # §1103-#7
        ("specialists", "dispatcher", True),
        ("ids", "errors", False),  # foundation: ids depends on errors
    ],
)
@pytest.mark.unit
def test_specific_boundary_rules(src_module: str, target: str, must_fail: bool) -> None:
    violations = mb.check_imports(src_module, [mb.Import(line=1, module=f"sdlc.{target}")])
    if must_fail:
        assert len(violations) == 1, f"{src_module}/ -> {target}/ should fail"
        assert target in violations[0]
    else:
        assert violations == [], f"{src_module}/ -> {target}/ should pass"


# ---------------------------------------------------------------------------
# check_imports — per-rule §1103-#N citation in error messages (D1/P11)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "src,tgt,rule",
    [
        # Rule #4: engine cannot import dashboard.
        ("engine", "dashboard", 4),
        # Rule #5: hooks/ cannot import engine/ or dispatcher/.
        ("hooks", "engine", 5),
        ("hooks", "dispatcher", 5),
        # Rule #6: adopt/ cannot import engine/ or dispatcher/.
        ("adopt", "engine", 6),
        ("adopt", "dispatcher", 6),
        # Rule #7: workflows/specialists cannot import engine/dispatcher/runtime.
        ("workflows", "engine", 7),
        ("specialists", "runtime", 7),
    ],
)
@pytest.mark.unit
def test_specific_rule_citation_in_message(src: str, tgt: str, rule: int) -> None:
    violations = mb.check_imports(src, [mb.Import(line=7, module=f"sdlc.{tgt}")])
    assert len(violations) == 1
    assert f"§1103-#{rule}" in violations[0], violations[0]


# ---------------------------------------------------------------------------
# check_imports — leaf-module rule (§1054 / §1103-#8)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_errors_module_cannot_import_anything() -> None:
    violations = mb.check_imports("errors", [mb.Import(line=1, module="sdlc.ids")])
    assert len(violations) == 1
    assert "errors/" in violations[0]
    assert "leaf" in violations[0].lower()
    assert "§1054" in violations[0]
    assert "§1103-#8" in violations[0]


@pytest.mark.unit
def test_errors_module_reports_all_violations_not_just_first() -> None:
    violations = mb.check_imports(
        "errors",
        [
            mb.Import(line=1, module="sdlc.ids"),
            mb.Import(line=2, module="sdlc.contracts"),
        ],
    )
    assert len(violations) == 2


# ---------------------------------------------------------------------------
# check_imports — message wording (D2 hybrid)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_state_importing_engine_uses_hybrid_wording() -> None:
    violations = mb.check_imports("state", [mb.Import(line=10, module="sdlc.engine.auto_loop")])
    assert len(violations) == 1
    msg = violations[0]
    assert "state/ -> engine/" in msg
    # Hybrid wording: full forbidden set listed, not just the offending target.
    for forbidden in ("cli", "dispatcher", "engine", "runtime"):
        assert f"{forbidden}/" in msg, f"forbidden module {forbidden} missing from msg"
    assert "§1073 layered DAG" in msg
    assert "§1052 dependency-table row" in msg


@pytest.mark.unit
def test_state_importing_undeclared_dep_is_rejected() -> None:
    # runtime/ IS in state.forbidden_from; this fires the forbidden_from branch.
    violations = mb.check_imports("state", [mb.Import(line=5, module="sdlc.runtime")])
    assert len(violations) == 1
    assert "state/ -> runtime/" in violations[0]


@pytest.mark.unit
def test_dashboard_cannot_import_engine() -> None:
    # Note: §1103-#4 cites engine→dashboard (the read-only invariant); the
    # reverse direction (dashboard→engine) is forbidden by layering with no
    # specific-rule citation, so we only assert the prefix here.
    violations = mb.check_imports("dashboard", [mb.Import(line=5, module="sdlc.engine.scanner")])
    assert len(violations) == 1
    assert "dashboard/ -> engine/" in violations[0]


@pytest.mark.unit
def test_dispatcher_can_import_runtime_at_module_level() -> None:
    # dispatcher.depends_on includes "runtime"; allowed at module-level even
    # though §1103-#2 (ABC discipline) is a code-review concern.
    # NOTE: with SPECIFIC_RULE_MAP, dispatcher→runtime DOES fire because
    # we cite the rule on the forbidden_from branch only — runtime is in
    # depends_on, not forbidden_from, so this passes.
    violations = mb.check_imports("dispatcher", [mb.Import(line=1, module="sdlc.runtime.abc")])
    assert violations == []


@pytest.mark.unit
def test_relative_import_violation_is_reported() -> None:
    violations = mb.check_imports("state", [mb.Import(line=3, module="<RELATIVE>")])
    assert len(violations) == 1
    assert "relative import" in violations[0]
    assert "§1075" in violations[0]


# ---------------------------------------------------------------------------
# check_imports — `from sdlc import X` end-to-end (P2)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_from_sdlc_import_engine_in_state_is_rejected() -> None:
    """The historic bypass: `from sdlc import engine` inside state/ must be flagged."""
    tree = ast.parse("from sdlc import engine\n")
    imports = mb._extract_sdlc_imports(tree, src_module="state")
    violations = mb.check_imports("state", imports)
    assert len(violations) == 1
    assert "state/ -> engine/" in violations[0]
