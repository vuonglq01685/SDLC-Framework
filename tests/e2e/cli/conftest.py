"""Tier-1 CLI golden harness conftest (AC2, AC4, AC5).

Defines: assert_goldens helper, load_commands_yaml helper,
_NoDuplicateKeysLoader (copied from src/sdlc/runtime/mock.py per ADR-027),
_normalize_paths helper, _hash_journal_no_ts helper.

The cli_runner fixture lives in tests/e2e/conftest.py (parent) so it is also
available to tests/e2e/test_harness_anti_tautology.py.

Tier-1 is fully subprocess-driven — NEVER imports from src/sdlc/* internals.
Interacts only via the public CLI surface (subprocess), ensuring insensitivity
to internal refactors (AC2 load-bearing isolation).
"""

from __future__ import annotations

import difflib
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from e2e.conftest import _normalize_timestamps, _strip_uv_preamble

# ---------------------------------------------------------------------------
# Skip markers (mirrors tests/integration/test_walking_skeleton_e2e.py)
# ---------------------------------------------------------------------------

_SKIP_NO_UV = pytest.mark.skipif(
    shutil.which("uv") is None,
    reason="uv not on PATH — skipping subprocess e2e test",
)
_SKIP_WIN32 = pytest.mark.skipif(
    sys.platform == "win32",
    reason="journal.append_sync is POSIX-only; scan e2e skipped on Windows",
)


# ---------------------------------------------------------------------------
# Sentinels (PR12 — distinct sentinels for absent vs empty journals)
# ---------------------------------------------------------------------------

_NO_JOURNAL_SENTINEL: str = "<no-journal>\n"
_EMPTY_JOURNAL_SENTINEL: str = "<empty-journal>\n"
_NO_STATE_SENTINEL: str = "<no-state>\n"


# ---------------------------------------------------------------------------
# Schema-version contract (P19) — bumped when commands.yaml shape changes.
# ---------------------------------------------------------------------------

_COMMANDS_YAML_SCHEMA_VERSION: int = 1


# ---------------------------------------------------------------------------
# _NoDuplicateKeysLoader — copied from src/sdlc/runtime/mock.py:68-103
# Copy-paste is intentional per ADR-027 "pytest-only goldens are sufficient";
# do NOT extract a shared helper in 2A.0 to avoid premature abstraction.
# ---------------------------------------------------------------------------


class _NoDuplicateKeysLoader(yaml.SafeLoader):
    """SafeLoader subclass that raises on duplicate mapping keys."""


def _construct_unique_mapping(
    loader: yaml.SafeLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    if not isinstance(node, yaml.MappingNode):
        raise yaml.constructor.ConstructorError(
            None,
            None,
            f"expected a mapping node, but found {node.id}",
            node.start_mark,
        )
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)  # type: ignore[no-untyped-call]
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)  # type: ignore[no-untyped-call]
    return mapping


_NoDuplicateKeysLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_PROJECT_BASENAME_SENTINEL: str = "<PROJECT>"


def _normalize_paths(text: str, tmp_path: Path) -> str:
    """Replace absolute tmp_path with ``<TMP>`` sentinel and pytest-derived basename
    with ``<PROJECT>`` sentinel (AC5.3, PR1).

    Replaces:
      - ``str(tmp_path.resolve())`` → ``<TMP>`` (handles macOS ``/private/var/...``).
      - ``str(tmp_path)`` → ``<TMP>`` (literal form).
      - ``tmp_path.name`` → ``<PROJECT>`` (PR1: pytest's tmp_path basename derives
        from the test function name, so ``sdlc status`` echoing the project name
        — via ``Path(cwd).name`` — would otherwise lock the golden to that test's
        identity).

    Order matters: resolved form is replaced first because it is typically a
    superstring of the literal form. Basename is replaced LAST so it doesn't
    shadow longer path matches.

    Basename normalization is gated by ``\\b`` word-boundary regex so an
    incidental substring inside another identifier is left alone.
    """
    import re

    resolved = str(tmp_path.resolve())
    literal = str(tmp_path)
    if resolved != literal:
        text = text.replace(resolved, "<TMP>")
    text = text.replace(literal, "<TMP>")
    # PR1: replace the bare basename only at word boundaries so partial matches
    # in unrelated identifiers are not corrupted.
    basename = tmp_path.name
    if basename:
        text = re.sub(rf"\b{re.escape(basename)}\b", _PROJECT_BASENAME_SENTINEL, text)
    return text


def _hash_journal_no_ts(journal_path: Path) -> str:  # noqa: C901  # 2A.5 DR3: per-kind canonicalization branches
    """Compute deterministic journal hash excluding ``ts`` (AC5.1).

    Re-canonicalizes each entry without ``ts`` (and without ``before/after_hash``
    for ``hooks_trusted`` kind, which references the wall-clock hook-hashes.json)
    and hashes the result. Returns ``<no-journal>`` for absent/empty file or
    ``<empty-journal>`` when no non-blank entries exist (PR12 distinct sentinels
    so regression-to-empty is not laundered as absence). Raises ``AssertionError``
    on malformed input pointing at journal-shape drift (P16).
    """
    if not journal_path.exists() or journal_path.stat().st_size == 0:
        return _NO_JOURNAL_SENTINEL
    raw_lines = journal_path.read_bytes().splitlines()
    canon_lines: list[bytes] = []
    for lineno, line in enumerate(raw_lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            decoded = stripped.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AssertionError(
                f"Journal corruption at {journal_path}:{lineno} — "
                f"line is not valid UTF-8: {exc}. "
                f"action: regenerate goldens or investigate journal writer."
            ) from exc
        try:
            entry: object = json.loads(decoded)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"Journal corruption at {journal_path}:{lineno} — "
                f"line is not valid JSON: {exc}. "
                f"action: regenerate goldens or investigate journal writer."
            ) from exc
        if not isinstance(entry, dict):
            raise AssertionError(
                f"Journal shape drift at {journal_path}:{lineno} — "
                f"expected a JSON object, got {type(entry).__name__}. "
                f"action: investigate journal writer for shape drift."
            )
        entry.pop("ts", None)
        if (
            entry.get("kind") == "hooks_trusted"
        ):  # Story 2A.5 DR3: strip refs to wall-clock hook-hashes.json
            entry.pop("before_hash", None)
            entry.pop("after_hash", None)
        canon = json.dumps(entry, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        canon_lines.append(canon)

    # PR12: file present but no canonical entries → distinct ``<empty-journal>``
    # sentinel so empty-journal regressions are not laundered as "no journal".
    if not canon_lines:
        return _EMPTY_JOURNAL_SENTINEL

    combined = b"\n".join(canon_lines)
    return hashlib.sha256(combined).hexdigest() + "\n"


def _validate_commands_entry(
    commands_yaml_path: Path,
    idx: int,
    cmd: object,
) -> None:
    """Validate a single commands.yaml entry. Raises AssertionError on shape drift.

    Required keys: ``id``, ``args``, ``flags`` (PR30 — was previously a dead-schema
    field; now required so a typo like ``flgs:`` is caught at load time).
    """
    if not isinstance(cmd, dict):
        raise AssertionError(
            f"{commands_yaml_path}: commands[{idx}] must be a mapping, got {type(cmd).__name__}"
        )
    for key in ("id", "args", "flags"):
        if key not in cmd:
            raise AssertionError(
                f"{commands_yaml_path}: commands[{idx}] missing required key {key!r}"
            )
    if not isinstance(cmd["args"], list):
        raise AssertionError(
            f"{commands_yaml_path}: commands[{idx}].args must be a list, "
            f"got {type(cmd['args']).__name__}"
        )
    if not isinstance(cmd["flags"], list):
        raise AssertionError(
            f"{commands_yaml_path}: commands[{idx}].flags must be a list, "
            f"got {type(cmd['flags']).__name__}"
        )


def load_commands_yaml(commands_yaml_path: Path) -> dict[str, object]:
    """Load commands.yaml with duplicate-key detection + schema validation (P9, P19).

    Raises:
      AssertionError on schema-version mismatch, missing top-level keys, or
      malformed command items. Errors include the offending path / index /
      key so authors can fix the YAML without trial-and-error.
    """
    raw = yaml.load(
        commands_yaml_path.read_text(encoding="utf-8"),
        Loader=_NoDuplicateKeysLoader,
    )
    if not isinstance(raw, dict):
        raise AssertionError(
            f"{commands_yaml_path}: top-level must be a mapping, got {type(raw).__name__}"
        )
    spec: dict[str, object] = raw

    # P19: schema_version is now enforced rather than theatre.
    schema_version = spec.get("schema_version")
    if schema_version != _COMMANDS_YAML_SCHEMA_VERSION:
        raise AssertionError(
            f"{commands_yaml_path}: schema_version mismatch — "
            f"expected {_COMMANDS_YAML_SCHEMA_VERSION}, got {schema_version!r}"
        )

    # P9: validate `commands` shape and per-item required fields.
    commands = spec.get("commands")
    if not isinstance(commands, list):
        raise AssertionError(
            f"{commands_yaml_path}: 'commands' must be a list, got {type(commands).__name__}"
        )
    for idx, cmd in enumerate(commands):
        _validate_commands_entry(commands_yaml_path, idx, cmd)

    return spec


# ---------------------------------------------------------------------------
# Central assertion helper
# ---------------------------------------------------------------------------
# PR24: ``golden_dir`` fixture removed — no test consumed it (P11's "OR remove"
# branch was the YAGNI choice). Reintroduce when a second scenario actually
# needs nodeid-based scenario resolution.


def _compare_one_golden(
    filename: str,
    actual: str,
    goldens_dir: Path,
    action_hint: str,
) -> str | None:
    """Return an error string if golden mismatches, or None if it matches."""
    golden_path = goldens_dir / filename
    if not golden_path.exists():
        return f"Golden file missing: {golden_path}\n{action_hint}"
    try:
        expected = golden_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return (
            f"GOLDEN MISMATCH: {golden_path}\n"
            f"  Golden file contains invalid UTF-8 bytes (corrupted).\n"
            f"{action_hint}"
        )
    if actual == expected:
        return None
    if filename.endswith(".sha256"):
        return (
            f"GOLDEN MISMATCH: {golden_path}\n"
            f"  expected: {expected.strip()!r}\n"
            f"  actual:   {actual.strip()!r}\n"
            f"{action_hint}"
        )
    diff = "".join(
        difflib.unified_diff(
            expected.splitlines(keepends=True),
            actual.splitlines(keepends=True),
            fromfile=f"expected/{filename}",
            tofile=f"actual/{filename}",
        )
    )
    return f"GOLDEN MISMATCH: {golden_path}\n{diff}\n{action_hint}"


def assert_goldens(
    scenario_dir: Path,
    command_id: str,
    result: subprocess.CompletedProcess[str],
    sdlc_dir: Path,
    tmp_path: Path,
    update: bool,
) -> None:
    """Assert (or update) the five golden files for a CLI command invocation (AC2.3-2.5).

    Golden files under <scenario_dir>/goldens/:
      <command_id>.stdout       — normalized stdout (paths + timestamps replaced)
      <command_id>.stderr       — uv-preamble-stripped, normalized stderr
      <command_id>.exit         — decimal exit code + newline
      <command_id>.journal_sha256 — ts-excluded journal content hash + newline
      <command_id>.state_sha256 — raw-bytes state hash + newline

    On mismatch, emits a unified diff (text goldens) or expected/actual lines
    (hash goldens), plus the standard re-generation instruction per ADR-027.

    Path conventions reflect the actual state writer (per the 2026-05-10 P26/D3
    spec amendment): ``<sdlc_dir>/state/journal.log`` + ``state.json``.

    PR21: ``result`` is now typed as ``subprocess.CompletedProcess[str]`` (was
    ``object``) so callers receive proper mypy --strict feedback.
    """
    goldens_dir = scenario_dir / "goldens"
    goldens_dir.mkdir(parents=True, exist_ok=True)

    raw_stdout = _normalize_paths(result.stdout, tmp_path)
    raw_stdout = _normalize_timestamps(raw_stdout)
    actual_stdout = raw_stdout

    raw_stderr = _normalize_paths(_strip_uv_preamble(result.stderr), tmp_path)
    raw_stderr = _normalize_timestamps(raw_stderr)
    actual_stderr = raw_stderr

    actual_exit = f"{result.returncode}\n"

    journal_path = sdlc_dir / "state" / "journal.log"
    state_path = sdlc_dir / "state" / "state.json"

    # PR12: distinct sentinels — _hash_journal_no_ts handles both absent and
    # whitespace-only-content cases internally.
    actual_journal_hash = _hash_journal_no_ts(journal_path)
    actual_state_hash = (
        hashlib.sha256(state_path.read_bytes()).hexdigest() + "\n"
        if state_path.exists()
        else _NO_STATE_SENTINEL
    )

    goldens: dict[str, str] = {
        f"{command_id}.stdout": actual_stdout,
        f"{command_id}.stderr": actual_stderr,
        f"{command_id}.exit": actual_exit,
        f"{command_id}.journal_sha256": actual_journal_hash,
        f"{command_id}.state_sha256": actual_state_hash,
    }

    if update:
        for filename, content in goldens.items():
            (goldens_dir / filename).write_text(content, encoding="utf-8")
        return

    _action_hint = (
        "action: review the diff. If intentional, regenerate via "
        "'pytest tests/e2e/cli/ --update-goldens' and cite the change in the PR Change Log."
    )

    errors = [
        err
        for filename, actual in goldens.items()
        if (err := _compare_one_golden(filename, actual, goldens_dir, _action_hint))
    ]

    if errors:
        raise AssertionError("\n\n".join(errors))
