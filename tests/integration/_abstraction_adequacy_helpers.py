"""Private helper module for abstraction-adequacy CI test (Story 1.14 / 2B.3).

Factored out of test_abstraction_adequacy.py so tests/unit/integration/ can import
helpers without cross-module test import ambiguity. Single-underscore prefix marks
this as private but keeps it importable for unit-test seams.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import shutil
import sys
import textwrap
import unicodedata
from collections.abc import Callable, Mapping
from functools import partial
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

import pytest
import yaml

from sdlc.contracts.hook_payload import HookPayload
from sdlc.contracts.journal_entry import JournalEntry
from sdlc.hooks.builtin.naming_validator import naming_validator
from sdlc.hooks.builtin.phase_gate import phase_gate
from sdlc.hooks.payload import build_write_intent_payload
from sdlc.hooks.runner import HookDecision, run_hook_chain
from sdlc.runtime import AgentResult, AIRuntime
from sdlc.signoff import compute_state
from sdlc.state.model import State

_SEED_PROMPT: Final[str] = "abstraction-adequacy seed prompt"
_SEED_CONTEXT: Final[Mapping[str, object]] = MappingProxyType(
    {"workflow_step": "abstraction-adequacy"}
)
_FROZEN_TS: Final[str] = "2026-05-08T00:00:00Z"
_ACTOR: Final[str] = "agent:abstraction-adequacy"
_SEED_TARGET_PATH: Final[str] = "01-Requirement/04-Epics/EPIC-abstraction-adequacy.json"
_ZERO_HASH: Final[str] = "sha256:" + "0" * 64
# Must match state.projection._EPIC_ID_PATTERN = r"\Aepic-[0-9]+\Z" — otherwise
# project_from_journal silently drops the epic-mutation branch and the goldens validate
# only next_monotonic_seq advancement (the abstraction-adequacy gate's main coverage
# surface). Pinned to the matching shape "epic-1" by review of Story 1.14; coverage
# of the pin lives in tests/unit/integration/test_abstraction_adequacy_helpers.py.
_TARGET_ID: Final[str] = "epic-1"

# ASCII "--" not em-dash: an editor unicode-normalization pass must not silently break the
# AC3 marker match (review P22). The seed YAML's leading comment carries the same ASCII form.
_EXTENSIBILITY_DOC_MARKER: Final[str] = "Story 2B.3 -- add a specialist (3-step checklist)"


def _normalize_strings(obj: Any) -> Any:
    """Recursively NFC-normalize string values.

    Mirror of sdlc.state.atomic._normalize_strings (Architecture §513). Duplicated
    locally so the helper module stays Windows-importable (state.atomic is POSIX-only,
    raises ImportError at module top on Windows).
    """
    if isinstance(obj, str):
        return unicodedata.normalize("NFC", obj)
    if isinstance(obj, dict):
        return {k: _normalize_strings(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_strings(item) for item in obj]
    return obj


def _canonicalize_state_for_hash(state: State) -> bytes:
    """Hash-canonical form: NFC-normalized, no trailing newline (Architecture §513).

    Differs from atomic._canonicalize_state in ONE place: no terminating b'\\n'
    (hash variant per §513). MUST otherwise match byte-for-byte, including the NFC
    normalization pass — divergence here masks unicode-edge bugs that the on-disk
    canonicalizer would catch.
    """
    payload = _normalize_strings(state.model_dump(mode="json"))
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _state_hash(state: State) -> str:
    """Return sha256:<hex> of the hash-canonical state bytes."""
    return "sha256:" + hashlib.sha256(_canonicalize_state_for_hash(state)).hexdigest()


def _format_diff(label: str, expected: bytes, actual: bytes) -> str:
    """Unified diff of two UTF-8 byte streams (AC2/D1).

    Relies on ``difflib``'s own ``--- ``/``+++ `` file headers; a manual header is NOT
    prepended (that duplicated difflib's output — review P7).
    """
    expected_lines = expected.decode("utf-8").splitlines(keepends=True)
    actual_lines = actual.decode("utf-8").splitlines(keepends=True)
    diff = "".join(
        difflib.unified_diff(
            expected_lines,
            actual_lines,
            fromfile=f"expected ({label})",
            tofile=f"actual ({label})",
        )
    )
    return f"{label} diverged:\n{diff}"


def fail_if_xdist_parallel(config: Any) -> None:
    """Fail loud if running under pytest-xdist (review P31 / Story 2B.3 D2=b).

    Per-runtime bytes live in a module-global dict (``_abstraction_adequacy_capture``); under
    xdist each worker gets its own copy, so the mock/claude captures never meet and the
    cross-runtime check would silently no-op. Fail loud rather than pass vacuously.
    """
    if getattr(config, "workerinput", None) is not None:
        pytest.fail(
            "abstraction-adequacy conformance harness is incompatible with pytest-xdist "
            "(per-runtime captures live in a module-global dict that does not cross workers); "
            "run it on a single worker, e.g. `-p no:xdist` or `-n0`",
            pytrace=False,
        )


def _signoff_reader(phase: int, repo_root: Path) -> str:
    return compute_state(phase, repo_root=repo_root).value


def build_conformance_hook_chain(
    repo_root: Path,
) -> tuple[Callable[[HookPayload], HookDecision], ...]:
    """Pre-write hook chain mirroring dispatcher wiring without importing dispatcher/."""
    bound_phase_gate = partial(
        phase_gate,
        repo_root=repo_root,
        signoff_reader=_signoff_reader,
    )
    bound_phase_gate.__is_phase_gate__ = True  # type: ignore[attr-defined]
    return (naming_validator, bound_phase_gate)


def _tool_call_target_and_hash(result: AgentResult) -> tuple[str, str]:
    if not result.tool_calls:
        raise ValueError(
            "conformance hook payload expects exactly one tool_call in v1 fixtures; got empty"
        )
    tool_call = result.tool_calls[0]
    try:
        args = tool_call["args"]
        if not isinstance(args, Mapping):
            raise TypeError(f"tool_call['args'] must be a Mapping; got {type(args).__name__}")
        target = args["target"]
        content_hash = args["content_hash"]
    except (KeyError, TypeError) as exc:
        raise ValueError(
            "tool_call shape mismatch — expected {name, args:{target, content_hash}};"
            f" missing/wrong key: {exc}"
        ) from exc
    if not isinstance(target, str):
        raise ValueError(f"tool_call['args']['target'] must be str; got {type(target).__name__}")
    if not isinstance(content_hash, str):
        raise ValueError(
            f"tool_call['args']['content_hash'] must be str; got {type(content_hash).__name__}"
        )
    return target, content_hash


def _build_pre_chain_input_payload(result: AgentResult, seq: int) -> HookPayload:
    """Build the HookPayload that is the INPUT to ``run_hook_chain`` (Story 2B.3).

    This helper SYNTHESISES the payload fed into the pre-write chain; it does NOT capture
    what the chain emits. AC1/D2 D1 ("the dispatched chain emits HookPayloads") is honoured
    via the load-bearing ``decision == "allow"`` invariant asserted in
    ``run_pre_write_hooks_for_dispatches`` — not via emission capture. Full emission capture
    is deferred to CR2B3-W13 / EPIC-2B-DEBT-CHAIN-EMISSION-CAPTURE (see deferred-work.md).
    """
    if not result.tool_calls:
        # COINCIDENCE-COUPLING (CR2B3-W12): Claude v1 parses stdout only, so its tool_calls
        # stay empty and this fallback hard-codes the seed's target/hash (_SEED_TARGET_PATH /
        # _ZERO_HASH); Mock reaches the same values via _tool_call_target_and_hash. A seed edit
        # changing either would silently DECOUPLE the runtimes — pinned RED by
        # test_seed_fixture_tool_call_matches_conformance_fallback_constants. Resolved by
        # surfacing tool_calls from the Claude parser: EPIC-2B-DEBT-CLAUDE-TOOL-CALLS.
        target = _SEED_TARGET_PATH
        content_hash = _ZERO_HASH
    else:
        target, content_hash = _tool_call_target_and_hash(result)
    return build_write_intent_payload(
        hook_name="pre_write",
        target_path=target,
        write_intent="create",
        content_hash_before=None if seq == 0 else content_hash,
    )


async def dispatch_twice(runtime: AIRuntime) -> tuple[AgentResult, AgentResult]:
    """Await two sequential dispatches inside a SINGLE event loop (review P24/P25).

    One ``asyncio.run`` wrapping two awaits — two separate ``asyncio.run`` calls churn the loop
    and trip a teardown DeprecationWarning under ``filterwarnings=["error"]`` (spec line 131).
    Shared by the main conformance test and the anti-tautology receipt. Do NOT split it.
    """
    first = await runtime.dispatch(_SEED_PROMPT, _SEED_CONTEXT)
    second = await runtime.dispatch(_SEED_PROMPT, _SEED_CONTEXT)
    return first, second


async def run_pre_write_hooks_for_dispatches(
    *,
    repo_root: Path,
    journal_path: Path,
    results: tuple[AgentResult, AgentResult],
) -> list[HookPayload]:
    """Invoke real ``run_hook_chain`` for each dispatch result; return payloads exercised."""
    hooks = build_conformance_hook_chain(repo_root)
    payloads: list[HookPayload] = []
    for seq, result in enumerate(results):
        payload = _build_pre_chain_input_payload(result, seq)
        decision = await run_hook_chain(
            payload,
            hooks=hooks,
            journal_path=journal_path,
        )
        assert decision.decision == "allow", (
            f"pre-write hook chain denied conformance write at seq={seq}: "
            f"{decision.reason!r} ({decision.error_code})"
        )
        payloads.append(payload)
    return payloads


def _build_claude_stub_script(responses_yaml: Path, target_dir: Path) -> Path:
    """Write executable ``claude`` stub reading ``responses_yaml`` (AC1/D1).

    Callers mkdir ``target_dir`` first, so this writer does not (P28). The stub uses
    ``sys.executable`` (P11 — a bare ``python3`` may lack PyYAML), reads stdin as bytes then
    decodes UTF-8 (P12), writes stdout with no trailing newline (P14 — byte-stable), and emits
    an ``is_error=True`` envelope on failure (P13 — actionable CI diagnostic).
    """
    stub_path = target_dir / "claude"
    script = textwrap.dedent(
        f'''\
        #!{sys.executable}
        """Auto-generated stub: echo Claude CLI JSON for abstraction-adequacy seed."""
        from __future__ import annotations

        import hashlib
        import json
        import sys
        from pathlib import Path

        import yaml


        def _emit_error(message: str) -> "int":
            sys.stdout.write(
                json.dumps(
                    {{"type": "result", "subtype": "error", "is_error": True, "result": message}}
                )
            )
            return 1


        def _main() -> "int":
            fixture = Path({str(responses_yaml)!r})
            prompt = sys.stdin.buffer.read().decode("utf-8")
            prompt_hash = "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            data = yaml.safe_load(fixture.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or prompt_hash not in data:
                return _emit_error(f"no fixture for prompt_hash={{prompt_hash}}")
            row = data[prompt_hash]
            try:
                envelope = {{
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "result": row["output_text"],
                    "usage": {{
                        "input_tokens": row["tokens_in"],
                        "output_tokens": row["tokens_out"],
                    }},
                }}
            except (KeyError, TypeError) as exc:
                return _emit_error(f"malformed fixture row for {{prompt_hash}}: {{exc!r}}")
            sys.stdout.write(json.dumps(envelope))
            return 0


        raise SystemExit(_main())
        '''
    )
    stub_path.write_text(script, encoding="utf-8")
    stub_path.chmod(0o755)
    return target_dir


def _build_claude_stub_for_fixture(fixture_path: Path, target_dir: Path) -> Path:
    """Generate a deterministic ``claude`` stub from the seed YAML (AC1/D1).

    Returns the directory to prepend to PATH (contains executable ``claude``).
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    responses_copy = target_dir / "abstraction_adequacy_responses.yaml"
    if fixture_path.resolve() != responses_copy.resolve():
        shutil.copy2(fixture_path, responses_copy)
    return _build_claude_stub_script(responses_copy, target_dir)


def _build_claude_stub_with_mutated_output(
    fixture_path: Path, target_dir: Path, *, target_key: str | None = None
) -> Path:
    """Stub like AC1/D1 but mutates ONE row's ``output_text`` by one byte (AC5 receipt #1).

    Single-row mutation (``target_key`` or the first row) keeps divergence localised; mutating
    ALL rows would break AC3 extensibility once the seed grows past one specialist (review P9).
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    raw = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError("fixture must be a mapping")
    mutable_rows = [
        key for key, row in raw.items() if isinstance(row, dict) and "output_text" in row
    ]
    if not mutable_rows:
        raise ValueError("fixture has no row with an 'output_text' field to mutate")
    key_to_mutate = target_key if target_key is not None else mutable_rows[0]
    if key_to_mutate not in mutable_rows:
        raise KeyError(f"target_key={key_to_mutate!r} not a mutable row in fixture")
    mutated = dict(raw)
    row = raw[key_to_mutate]
    mutated[key_to_mutate] = {**row, "output_text": str(row["output_text"]) + "X"}
    mutated_path = target_dir / "abstraction_adequacy_responses.yaml"
    mutated_path.write_text(
        yaml.safe_dump(mutated, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return _build_claude_stub_script(mutated_path, target_dir)


def seed_fixture_has_extensibility_doc(fixture_path: Path) -> bool:
    """True when the AC3 leading comment block is present."""
    text = fixture_path.read_text(encoding="utf-8")
    return _EXTENSIBILITY_DOC_MARKER in text


def _build_journal_entry(
    seq: int,
    before_hash: str | None,
    after_hash: str,
    agent_result: AgentResult,
) -> JournalEntry:
    """Build a JournalEntry for one pipeline step.

    tool_calls are intentionally NOT in the payload — they are captured by HookPayload
    synthesis. Duplicating them here would make the journal a secondary source of truth
    for the hook surface, violating the substrate's separation of concerns.

    ``mock`` IS written into the payload (mirroring the production dispatcher; review P34/D5)
    so the projection strip (AC4) is exercised by the integration pipeline — Mock writes
    ``mock=True``, Claude ``mock=False``, yet state.json stays byte-identical (the projection
    filters _AUDIT_ONLY_KEYS).
    """
    return JournalEntry(
        schema_version=1,
        monotonic_seq=seq,
        ts=_FROZEN_TS,
        actor=_ACTOR,
        kind="state_mutation",
        target_id=_TARGET_ID,
        before_hash=before_hash,
        after_hash=after_hash,
        payload={
            "output_text": agent_result.output_text,
            "tokens_in": agent_result.tokens_in,
            "tokens_out": agent_result.tokens_out,
            "mock": agent_result.mock,
        },
    )


def install_claude_stub_on_path(
    monkeypatch: Any,
    fixture_path: Path,
    tmp_path: Path,
    *,
    mutate_output: bool = False,
) -> None:
    """Place generated stub on PATH for ClaudeAIRuntime discovery."""
    bindir = tmp_path / "claude-stub-bin"
    if mutate_output:
        _build_claude_stub_with_mutated_output(fixture_path, bindir)
    else:
        _build_claude_stub_for_fixture(fixture_path, bindir)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")
