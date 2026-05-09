"""Module boundary + LOC cap enforcement for src/sdlc/ (ADR-010, Story 1.4).

Encodes Architecture §1052-§1112 dependency table as MODULE_DEPS and the
8 §1103 rules as SPECIFIC_RULE_MAP. Walks Python files passed on argv,
AST-parses imports, asserts each import target is allowed given the source
module, and asserts file LOC ≤ 400.

Exit codes: 0 = clean, 1 = boundary/LOC violation. Syntax errors are silently
skipped (ruff gates syntax separately).
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModuleSpec:
    depends_on: frozenset[str]
    forbidden_from: frozenset[str]


FOUNDATION = frozenset({"errors", "ids", "contracts", "config", "concurrency"})
UPPER_STACK = frozenset({"engine", "dispatcher", "cli"})

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
        # state depends on journal: state.json is a projection of the journal
        # (Decision B5, ADR-015 / Story 1.12).
        depends_on=frozenset({"errors", "contracts", "concurrency", "config", "journal"}),
        forbidden_from=frozenset({"engine", "dispatcher", "runtime", "cli"}),
    ),
    "journal": ModuleSpec(
        depends_on=frozenset({"errors", "contracts", "concurrency", "config"}),
        forbidden_from=frozenset({"engine", "dispatcher", "runtime", "cli"}),
    ),
    "signoff": ModuleSpec(
        depends_on=frozenset({"errors", "contracts", "state", "journal"}),
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
    "specialists": ModuleSpec(
        depends_on=frozenset({"errors", "contracts", "workflows"}),
        forbidden_from=frozenset({"engine", "dispatcher", "runtime"}),
    ),
    "hooks": ModuleSpec(
        depends_on=frozenset({"errors", "contracts", "state", "journal", "ids"}),
        forbidden_from=frozenset({"engine", "dispatcher", "runtime", "cli"}),
    ),
    "telemetry": ModuleSpec(
        depends_on=frozenset({"errors", "contracts", "journal"}),
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
            }
        ),
        forbidden_from=frozenset({"engine", "cli"}),
    ),
    "engine": ModuleSpec(
        depends_on=frozenset(
            {
                "errors",
                "ids",  # NEW (Story 1.15) — scanner.py needs parse_epic_id/_story_id/_task_id
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
        # `dashboard` is forbidden so §1103-#4 cites cleanly — dashboard is
        # read-only re state/journal; engine importing dashboard inverts the
        # layered DAG (`dashboard` sits below the upper stack, not parallel).
        forbidden_from=frozenset({"cli", "dashboard"}),
    ),
    # Known widening vs. Architecture §1069: adopt/ may only use cli/git
    # sub-import, but at module-level granularity we grant adopt→cli (recorded
    # in ADR-010 Consequences as a known gap).
    "adopt": ModuleSpec(
        depends_on=frozenset({"errors", "state", "journal", "signoff", "config"}),
        forbidden_from=frozenset({"engine", "dispatcher", "runtime"}),
    ),
    # Story 1.19 / ADR-022: migration scripts are a leaf cluster (errors + state only).
    "migrations": ModuleSpec(
        depends_on=frozenset({"errors", "state"}),
        forbidden_from=frozenset({"engine", "dispatcher", "runtime", "cli"}),
    ),
    # Known gap: "read-only" constraint is not expressible at import-graph level (ADR-010).
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
                # Story 1.16 widening: cli/init.py + cli/scan.py (Story 1.17) +
                # cli/rebuild_state.py (Story 1.20) need direct state/journal I/O.
                "state",  # cli/init.py writes state.json via write_state_atomic_sync
                "journal",  # cli/init.py creates empty journal.log; cli/scan.py appends
                "contracts",  # JournalEntry / State pydantic contracts used by cli
                "ids",  # cli/init.py + cli/scan.py validate canonical IDs
                "migrations",  # cli/migrate.py dispatches migration scripts (Story 1.19)
            }
        ),
        forbidden_from=frozenset(),
    ),
    # Provisional v0.2 entry: agents/ holds the specialist registry (markdown +
    # frontmatter today; will gain Python with Story 2A-2). Conservative leaf
    # profile prevents silent bypass when the first .py lands here.
    # TODO Story 2A-2: revise based on actual specialist runtime requirements.
    "agents": ModuleSpec(
        depends_on=frozenset({"errors", "contracts", "workflows", "specialists"}),
        forbidden_from=frozenset({"engine", "dispatcher", "runtime", "cli", "state", "journal"}),
    ),
}


SPECIFIC_RULE_MAP: dict[tuple[str, str], int] = {
    ("engine", "dashboard"): 4,  # #4
    ("hooks", "engine"): 5,
    ("hooks", "dispatcher"): 5,  # #5
    ("adopt", "engine"): 6,
    ("adopt", "dispatcher"): 6,  # #6
    ("workflows", "engine"): 7,
    ("workflows", "dispatcher"): 7,  # #7
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


# Path helpers

SDLC_ROOT = Path("src/sdlc")


def file_to_module(p: Path, sdlc_root: Path | None = None) -> str | None:
    """Return module name for paths under src/sdlc/<module>/...; None otherwise."""
    root = sdlc_root if sdlc_root is not None else SDLC_ROOT
    try:
        rel = p.resolve().relative_to(root.resolve())
    except ValueError:
        return None  # not under src/sdlc/
    parts = rel.parts
    if not parts or parts[0] == "__init__.py":
        return None  # the package root itself
    candidate = parts[0]
    if (root / candidate).is_dir():
        return candidate
    # Top-level flat-file submodule, e.g. src/sdlc/version.py -> 'version'.
    if len(parts) == 1 and candidate.endswith(".py"):
        return candidate[: -len(".py")]
    return None


@dataclass(frozen=True)
class Import:
    line: int
    module: str  # fully-qualified, e.g. "sdlc.engine.auto_loop"


def _is_type_checking_block(node: ast.If) -> bool:
    """True if `node` is `if TYPE_CHECKING:` or `if typing.TYPE_CHECKING:`."""
    test = node.test
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"


def _process_import_stmt(node: ast.Import, out: list[Import]) -> None:
    """Extract sdlc.* modules from import statements."""
    for alias in node.names:
        if alias.name.startswith("sdlc.") or alias.name == "sdlc":
            out.append(Import(line=node.lineno, module=alias.name))


def _process_import_from(node: ast.ImportFrom, out: list[Import], src_module: str | None) -> bool:
    """Extract sdlc.* modules from from-import statements. Return True if skip children."""
    # Flag relative imports inside src/sdlc/<module>/ files (Architecture §1075).
    if node.level and node.level > 0 and src_module is not None:
        out.append(Import(line=node.lineno, module="<RELATIVE>"))
        return True
    if node.module is None:
        return True
    if node.module == "sdlc":
        for alias in node.names:
            out.append(Import(line=node.lineno, module=f"sdlc.{alias.name}"))
        return True
    if node.module.startswith("sdlc."):
        out.append(Import(line=node.lineno, module=node.module))
        return True
    return False


def _walk_ast_tree(node: ast.AST, out: list[Import], src_module: str | None) -> None:
    """Recursively walk AST to extract imports, skipping TYPE_CHECKING blocks."""
    if isinstance(node, ast.If) and _is_type_checking_block(node):
        return  # skip body and orelse — type-only context
    if isinstance(node, ast.Import):
        _process_import_stmt(node, out)
    elif isinstance(node, ast.ImportFrom) and _process_import_from(node, out, src_module):
        return
    for child in ast.iter_child_nodes(node):
        _walk_ast_tree(child, out, src_module)


def _extract_sdlc_imports(tree: ast.AST, src_module: str | None = None) -> list[Import]:
    """Collect all sdlc.* absolute imports; flag relative imports in src/sdlc/ files.

    Imports under `if TYPE_CHECKING:` blocks are skipped (type-only, PEP 484).
    """
    out: list[Import] = []
    _walk_ast_tree(tree, out, src_module)
    return out


_SDLC_MIN_PARTS = 2  # "sdlc.<module>" requires at least two dot-separated segments


def _import_target_module(qualified: str) -> str | None:
    """sdlc.engine.auto_loop -> 'engine'; sdlc -> None (package itself)."""
    parts = qualified.split(".")
    return parts[1] if len(parts) >= _SDLC_MIN_PARTS and parts[0] == "sdlc" else None


def _format_forbidden_set(spec: ModuleSpec) -> str:
    """Render forbidden targets as `engine/dispatcher/runtime/cli` for messages."""
    return "/".join(sorted(spec.forbidden_from)) + "/" if spec.forbidden_from else ""


def check_imports(src_module: str, imports: list[Import]) -> list[str]:
    """Return list of human-readable violation messages."""
    spec = MODULE_DEPS.get(src_module)
    if spec is None:
        return []  # unknown module (e.g. typo subdir); ruff/mypy catches separately
    violations: list[str] = []
    for imp in imports:
        if imp.module == "<RELATIVE>":
            violations.append(
                f"{imp.line}: relative import in src/sdlc/{src_module}/ is forbidden; "
                f"use absolute `from sdlc.X import Y` (Architecture §1075)"
            )
            continue
        tgt = _import_target_module(imp.module)
        if tgt is None or tgt == src_module:
            continue  # bare `import sdlc` or self-import
        # errors/ is a leaf module: no sdlc.* imports allowed (§1054 + §1103-#8).
        if src_module == "errors":
            violations.append(
                f"{imp.line}: import violation: errors/ -> {tgt}/ "
                f"(errors/ is a leaf module; see Architecture §1054 + §1103-#8)"
            )
            continue
        if tgt in spec.forbidden_from:
            forbidden = _format_forbidden_set(spec)
            rule = SPECIFIC_RULE_MAP.get((src_module, tgt))
            rule_anchor = f" + §1103-#{rule}" if rule is not None else ""
            violations.append(
                f"{imp.line}: import violation: {src_module}/ -> {tgt}/ "
                f"({src_module}/ is forbidden from importing {forbidden}; "
                f"see Architecture §1073 layered DAG + §1052 dependency-table row{rule_anchor})"
            )
        elif tgt not in spec.depends_on:
            violations.append(
                f"{imp.line}: import violation: {src_module}/ -> {tgt}/ "
                f"({src_module}/ does not declare {tgt}/ as a dependency; "
                f"see Architecture §1052 dependency-table row)"
            )
    return violations


LOC_CAP = 400
# Path-prefix exemptions, expressed as `Path.parts` tuples so matching works
# correctly for absolute paths and on Windows (where str(Path) uses '\').
LOC_EXEMPT_PATH_PREFIX_PARTS: tuple[tuple[str, ...], ...] = (("tests", "fixtures"),)


def _is_loc_exempt(p: Path) -> bool:
    """True if any LOC_EXEMPT_PATH_PREFIX_PARTS appears as a contiguous run in p.parts."""
    parts = p.parts
    for prefix in LOC_EXEMPT_PATH_PREFIX_PARTS:
        n = len(prefix)
        for i in range(len(parts) - n + 1):
            if parts[i : i + n] == prefix:
                return True
    return False


def check_loc_cap(p: Path) -> list[str]:
    """Return a violation message if p exceeds LOC_CAP raw lines."""
    if _is_loc_exempt(p):
        return []
    # Raw line count: newline-delimited, matches Architecture §765 "≤ 400 LOC/file cap".
    # Equivalent to `wc -l` semantics for POSIX-clean files.
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []  # ruff/mypy catches; not our job
    lines = text.count("\n") + (0 if text.endswith("\n") or text == "" else 1)
    if lines > LOC_CAP:
        return [
            f"LOC cap exceeded: {p} has {lines} lines (cap: {LOC_CAP}; "
            f"see Architecture §765 + NFR-MAINT-3)"
        ]
    return []


def main(argv: list[str]) -> int:
    """Process each file path passed by pre-commit; return 0 (clean) or 1 (violations)."""
    violations: list[str] = []
    for path_str in argv:
        p = Path(path_str)
        if not p.exists() or p.suffix != ".py":
            continue
        violations.extend(check_loc_cap(p))
        module = file_to_module(p, sdlc_root=SDLC_ROOT)
        if module is None:
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue  # ruff catches syntax errors separately; not our job
        imports = _extract_sdlc_imports(tree, src_module=module)
        violations.extend(f"{p}:{msg}" for msg in check_imports(module, imports))
    if violations:
        print("\n".join(violations), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
