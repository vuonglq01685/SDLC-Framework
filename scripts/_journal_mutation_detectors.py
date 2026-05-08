"""AST detectors for ``check_no_journal_mutation.py`` (split out for ≤400 LOC cap).

Pure helpers — no module state, no side effects. The main script imports from here.
"""

from __future__ import annotations

import ast
import re

# Patterns that indicate a journal path argument. ``JOURNAL\b`` (no required suffix) catches
# bare ``JOURNAL`` constants; explicit alternations cover audit/event aliases.
_JOURNAL_PATH_NAMES = re.compile(
    r"(journal\.log|journal\.jsonl|journal_path|JOURNAL\b|audit\.log|audit\.jsonl|events\.log)",
    re.IGNORECASE,
)

# Write modes that create/overwrite/append files (all banned outside writer.py)
_WRITE_MODES = frozenset({"w", "wb", "a", "ab", "r+", "rb+", "w+", "wb+"})

# os flags that imply a write open (any of these = banned)
_OS_WRITE_FLAGS = frozenset({"O_WRONLY", "O_RDWR", "O_CREAT", "O_TRUNC", "O_APPEND"})

_MIN_ARGS = 2


def _is_journal_path_expr(node: ast.expr) -> bool:
    src = ast.unparse(node)
    return bool(_JOURNAL_PATH_NAMES.search(src))


def _flag_has_write_intent(flags_node: ast.expr) -> bool:
    """True if any name in the flags expression is a write-implying os.O_* constant."""
    for sub in ast.walk(flags_node):
        if isinstance(sub, ast.Attribute) and sub.attr in _OS_WRITE_FLAGS:
            return True
        if isinstance(sub, ast.Name) and sub.id in _OS_WRITE_FLAGS:
            return True
    return False


def _extract_mode(node: ast.Call) -> str | None:
    """Return the string mode from positional args[1] or ``mode=`` kwarg, or None."""
    if len(node.args) >= _MIN_ARGS:
        mode_arg = node.args[1]
        if isinstance(mode_arg, ast.Constant) and isinstance(mode_arg.value, str):
            return mode_arg.value
    for kw in node.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            if isinstance(kw.value.value, str):
                return kw.value.value
            return None
    return None


def _check_open_call(node: ast.Call) -> str | None:
    """Detect open(journal_path, write_mode) — also handles ``mode=`` kwarg bypass."""
    func = node.func
    is_open = (isinstance(func, ast.Name) and func.id == "open") or (
        isinstance(func, ast.Attribute) and func.attr == "open"
    )
    if not is_open or not node.args:
        return None
    mode_value = _extract_mode(node)
    if mode_value is None or mode_value not in _WRITE_MODES:
        return None
    if not _is_journal_path_expr(node.args[0]):
        return None
    return f"open() with mode '{mode_value}' on journal path"


def _check_os_open_call(node: ast.Call) -> str | None:
    """Detect ``os.open(journal_path, O_WRONLY|O_TRUNC|...)`` outside writer.py."""
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr != "open":
        return None
    if not isinstance(func.value, ast.Name):
        return None
    if len(node.args) < _MIN_ARGS:
        return None
    if not _is_journal_path_expr(node.args[0]):
        return None
    if not _flag_has_write_intent(node.args[1]):
        return None
    return "os.open() with write flags on journal path"


def _extract_path_method_mode(node: ast.Call) -> str | None:
    """Mode for ``Path(<x>).open("w")`` form — first positional arg or ``mode=`` kwarg."""
    if node.args:
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
    for kw in node.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            if isinstance(kw.value.value, str):
                return kw.value.value
            return None
    return None


def _check_path_method_open(node: ast.Call) -> str | None:
    """Detect ``Path(<journal>).open("w"|...)`` — path is on receiver, not args[0]."""
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr != "open":
        return None
    if not _is_journal_path_expr(func.value):
        return None
    mode_value = _extract_path_method_mode(node)
    if mode_value is None or mode_value not in _WRITE_MODES:
        return None
    return f"Path.open() with mode '{mode_value}' on journal path"


def _check_path_write_call(node: ast.Call) -> str | None:
    """Detect Path(journal_path).write_text/write_bytes(...)."""
    func = node.func
    if not isinstance(func, ast.Attribute):
        return None
    if func.attr not in {"write_text", "write_bytes"}:
        return None
    if not _is_journal_path_expr(func.value):
        return None
    return f"Path.{func.attr}() on journal path"


def _check_replace_call(node: ast.Call) -> str | None:
    """Detect os.replace/os.rename(<src>, journal_path) — replaces file in-place."""
    func = node.func
    if not isinstance(func, ast.Attribute):
        return None
    if func.attr not in {"replace", "rename"}:
        return None
    if not isinstance(func.value, ast.Name) or func.value.id != "os":
        return None
    if len(node.args) < _MIN_ARGS:
        return None
    dst_arg = node.args[1]
    if not _is_journal_path_expr(dst_arg):
        return None
    return f"os.{func.attr}() with journal path as destination"


def _check_truncate_call(node: ast.Call, os_aliases: frozenset[str]) -> str | None:
    """Detect ``os.truncate(<journal>, ...)`` and ``<expr>.truncate()`` on journal path."""
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr != "truncate":
        return None
    if isinstance(func.value, ast.Name) and func.value.id in os_aliases:
        if not node.args or not _is_journal_path_expr(node.args[0]):
            return None
        return "os.truncate() on journal path"
    if _is_journal_path_expr(func.value):
        return "<expr>.truncate() on journal path"
    return None


def _check_unlink_call(node: ast.Call, os_aliases: frozenset[str]) -> str | None:
    """Detect ``os.unlink(<journal>)`` and ``Path(<journal>).unlink()``."""
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr != "unlink":
        return None
    if isinstance(func.value, ast.Name) and func.value.id in os_aliases:
        if not node.args or not _is_journal_path_expr(node.args[0]):
            return None
        return "os.unlink() on journal path"
    if _is_journal_path_expr(func.value):
        return "Path.unlink() on journal path"
    return None


def _check_link_call(node: ast.Call, os_aliases: frozenset[str]) -> str | None:
    """Detect ``os.link(_, journal)`` / ``os.symlink(_, journal)``."""
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr not in {"link", "symlink"}:
        return None
    if not (isinstance(func.value, ast.Name) and func.value.id in os_aliases):
        return None
    if len(node.args) < _MIN_ARGS:
        return None
    if not _is_journal_path_expr(node.args[1]):
        return None
    return f"os.{func.attr}() with journal path as link target"


def _collect_os_aliases(tree: ast.Module) -> frozenset[str]:
    """Pre-walk the module's top-level imports collecting every alias of ``os``."""
    aliases: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "os":
                    aliases.add(alias.asname or alias.name)
    if not aliases:
        aliases.add("os")  # default — covers files that never imported os explicitly
    return frozenset(aliases)


def _collect_calls(scope: ast.AST) -> list[ast.Call]:
    """Collect Call nodes in document order, NOT descending into nested function bodies."""
    all_calls: list[ast.Call] = []
    skip_types = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)

    def _walk(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, skip_types):
                continue
            if isinstance(child, ast.Call):
                all_calls.append(child)
            _walk(child)

    _walk(scope)
    all_calls.sort(key=lambda c: (c.lineno, c.col_offset))
    return all_calls


def _collect_rebound_names(scope: ast.AST) -> set[str]:
    """Track Assign re-bindings of names so prior seek tracking can be reset."""
    rebound: set[str] = set()
    for node in ast.walk(scope):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    rebound.add(tgt.id)
    return rebound


def _find_seek_then_write_violations(scope: ast.AST) -> list[tuple[int, str]]:
    """Detect ``f.seek(...)`` then ``f.write(...)`` on the same handle within ``scope``."""
    violations: list[tuple[int, str]] = []
    seen_seeks: dict[str, int] = {}
    rebound = _collect_rebound_names(scope)
    for call in _collect_calls(scope):
        func = call.func
        if not isinstance(func, ast.Attribute):
            continue
        receiver_src = ast.unparse(func.value)
        if func.attr == "seek":
            if receiver_src in rebound:
                seen_seeks.pop(receiver_src, None)
            seen_seeks[receiver_src] = call.lineno
        elif func.attr == "write" and receiver_src in seen_seeks:
            violations.append((call.lineno, f"seek()+write() anti-pattern on '{receiver_src}'"))
    return violations


def _find_lseek_then_write_violations(
    scope: ast.AST, os_aliases: frozenset[str]
) -> list[tuple[int, str]]:
    """Detect ``os.lseek(fd, ...)`` then ``os.write(fd, ...)`` on the same fd-name."""
    violations: list[tuple[int, str]] = []
    seen_lseeks: dict[str, int] = {}
    for call in _collect_calls(scope):
        func = call.func
        if not isinstance(func, ast.Attribute):
            continue
        if not isinstance(func.value, ast.Name) or func.value.id not in os_aliases:
            continue
        if func.attr == "lseek" and call.args:
            seen_lseeks[ast.unparse(call.args[0])] = call.lineno
        elif func.attr == "write" and call.args:
            fd_src = ast.unparse(call.args[0])
            if fd_src in seen_lseeks:
                violations.append(
                    (call.lineno, f"os.lseek()+os.write() anti-pattern on fd '{fd_src}'")
                )
    return violations
