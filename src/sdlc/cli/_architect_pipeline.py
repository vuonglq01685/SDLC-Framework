"""Pipeline helpers for ``sdlc architect`` (Story 2A.14).

Extracted from cli/architect.py to keep that module under the 400-line cap.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import yaml

from sdlc.concurrency.io_primitives import atomic_write
from sdlc.contracts.hook_payload import HookPayload
from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.dispatcher import (
    PanelObserver,
    allocate_seq,
    content_hash,
    dispatch,
    make_journal_entry,
    now_ts,
    phase1_compound_prompt_builder,
    phase1_prompt_builder,
)
from sdlc.dispatcher.core import LegacyPromptBuilder
from sdlc.errors import SpecialistError, WorkflowError
from sdlc.hooks.payload import build_write_intent_payload
from sdlc.hooks.runner import HookDecision, run_hook_chain
from sdlc.journal import append as journal_append
from sdlc.runtime.mock import MockAIRuntime, compute_prompt_hash
from sdlc.specialists.frontmatter import Specialist
from sdlc.specialists.registry import SpecialistRegistry

_PRIMARY_SPECIALIST: str = "system-architect"
_PLACEHOLDER: str = "**PLACEHOLDER** — MockAIRuntime v1. Real content lands in Story 2B.9.\n"

_logger = logging.getLogger(__name__)


def parse_requires_block(arch_path: Path) -> list[str]:  # noqa: C901, PLR0911
    """Extract requires: list from ARCHITECTURE.md YAML frontmatter (AC6).

    Malformed or non-conforming frontmatter degrades to an empty list, but
    always emits a WARN log (AC6) so a genuine sub-track declaration is never
    silently dropped without an observable signal. Entries are whitespace-
    stripped, de-duplicated (first-seen order preserved), and non-string /
    empty entries are skipped with a WARN — never coerced via ``str()``.
    """
    text = arch_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return []
    end = text.find("\n---", 3)
    if end == -1:
        _logger.warning(
            "%s: opening '---' frontmatter has no closing delimiter; treating as no sub-tracks",
            arch_path,
        )
        return []
    frontmatter_text = text[3:end].strip()
    try:
        fm: object = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError as exc:
        _logger.warning(
            "%s: frontmatter is not valid YAML (%s); treating as no sub-tracks",
            arch_path,
            exc,
        )
        return []
    if not isinstance(fm, dict):
        return []
    if "requires" not in fm:
        return []
    requires = fm["requires"]
    if not isinstance(requires, list):
        _logger.warning(
            "%s: 'requires:' is %s, not a list; treating as no sub-tracks",
            arch_path,
            type(requires).__name__,
        )
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in requires:
        if not isinstance(item, str):
            _logger.warning(
                "%s: 'requires:' has a non-string entry %r; skipping",
                arch_path,
                item,
            )
            continue
        name = item.strip()
        if not name:
            _logger.warning("%s: 'requires:' has an empty entry; skipping", arch_path)
            continue
        if name in seen:
            _logger.warning(
                "%s: 'requires:' lists %r more than once; de-duplicated",
                arch_path,
                name,
            )
            continue
        seen.add(name)
        result.append(name)
    return result


def build_sub_track_prompt(
    sp: Specialist,
    wf: WorkflowSpec,
    *,
    product_text: str,
    arch_text: str,
) -> str:
    """Single source of truth for the sub-track compound prompt (AC7).

    Both ``materialize_sub_track_mock`` (which keys the MockAIRuntime fixture by
    ``compute_prompt_hash``) and the CLI's dispatch ``prompt_builder`` MUST route
    through this helper. If the two prompt-construction sites drift by even one
    character the fixture hash no longer matches and MockAIRuntime fails to
    resolve the canned response.
    """
    return phase1_compound_prompt_builder(
        sp,
        wf,
        primary_input=product_text,
        secondary_input=arch_text,
        primary_label="PRODUCT_BRIEF",
        secondary_label="SYSTEM_ARCHITECTURE",
        role="primary",
    )


def _write_fixture(dest_dir: Path, name: str, h: str, body: str) -> None:
    records = {h: {"output_text": body, "tokens_in": 1, "tokens_out": 1, "tool_calls": []}}
    atomic_write(
        dest_dir / f"{name}.yaml",
        yaml.safe_dump(records, sort_keys=True, allow_unicode=True),
    )


def materialize_primary_mock(
    dest_dir: Path,
    *,
    spec: WorkflowSpec,
    registry: SpecialistRegistry,
    product_text: str,
    requires: tuple[str, ...] | None = ("database", "security"),
) -> None:
    """Write MockAIRuntime fixture for the primary system-architect specialist.

    ``requires`` controls the ``requires:`` frontmatter the mock primary
    declares. The default exercises the happy path with two sub-tracks; callers
    pass ``None`` (no frontmatter → no sub-tracks) or other names to drive the
    no-sub-track and unknown-sub-track paths through the real runtime
    (Story 2A.14 code review CR14-P8/B1).
    """
    try:
        sp = registry.get(_PRIMARY_SPECIALIST)
    except (KeyError, SpecialistError) as exc:
        raise WorkflowError(
            f"system-architect specialist not registered: {exc}",
            details={"specialist": _PRIMARY_SPECIALIST, "cause": str(exc)},
        ) from exc

    assert isinstance(sp, Specialist)
    prompt = phase1_prompt_builder(
        sp, spec, idea_text=product_text, role="primary", upstream_outputs=()
    )
    sections = f"## Overview\n\n{_PLACEHOLDER}\n\n## Component Design\n\n{_PLACEHOLDER}\n"
    if requires:
        front = "".join(f"  - {r}\n" for r in requires)
        body = f"---\nrequires:\n{front}---\n\n{sections}"
    else:
        body = sections
    _write_fixture(dest_dir, spec.name, compute_prompt_hash(prompt), body)


def materialize_sub_track_mock(
    dest_dir: Path,
    *,
    sub_track: str,
    specialist_name: str,
    sub_spec: WorkflowSpec,
    registry: SpecialistRegistry,
    product_text: str,
    arch_text: str,
) -> None:
    """Write MockAIRuntime fixture for a sub-track specialist (AC7)."""
    try:
        sp = registry.get(specialist_name)
    except (KeyError, SpecialistError) as exc:
        raise WorkflowError(
            f"{specialist_name} specialist not registered: {exc}",
            details={"specialist": specialist_name, "cause": str(exc)},
        ) from exc

    assert isinstance(sp, Specialist)
    prompt = build_sub_track_prompt(sp, sub_spec, product_text=product_text, arch_text=arch_text)
    body = f"## {sub_track.title()} Architecture\n\n{_PLACEHOLDER}"
    _write_fixture(dest_dir, sub_spec.name, compute_prompt_hash(prompt), body)


async def dispatch_and_write(
    *,
    spec: WorkflowSpec,
    target_path: Path,
    rel_path: str,
    root: Path,
    journal_path: Path,
    agent_runs_path: Path,
    prompt_builder: LegacyPromptBuilder,
    runtime: MockAIRuntime,
    registry: SpecialistRegistry,
    hooks: tuple[Callable[[HookPayload], HookDecision], ...],
    specialist_name: str,
    slash_cmd: str,
) -> str:
    """Dispatch one specialist and write the result to disk. Returns output_text."""
    seq_ad = await allocate_seq(journal_path)
    await journal_append(
        make_journal_entry(
            seq=seq_ad,
            ts=now_ts(),
            kind="agent_dispatched",
            target_id=rel_path,
            payload={"slash_command": slash_cmd, "phase": 2, "specialist": specialist_name},
            actor="cli",
        ),
        journal_path,
    )

    observer = PanelObserver(slash_command=slash_cmd, emit_agent_dispatched=False)
    result = await dispatch(
        spec,
        runtime=runtime,
        registry=registry,
        repo_root=root,
        journal_path=journal_path,
        agent_runs_path=agent_runs_path,
        prompt_builder=prompt_builder,
        hooks=hooks,
        observer=observer,
        persist_artifact=False,
        target_path_override=target_path,
    )

    if result.outcome != "success":
        raise WorkflowError(
            f"architect dispatch finished with outcome={result.outcome!r}",
            details={"outcome": result.outcome, "specialist": specialist_name},
        )

    output_text = result.agent_result.output_text
    if not isinstance(output_text, str):
        raise WorkflowError(
            f"{specialist_name} agent_result.output_text must be a string",
            details={"actual_type": type(output_text).__name__},
        )

    before_hash: str | None = None
    if target_path.exists():
        try:
            before_hash = content_hash(target_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            before_hash = None

    payload = build_write_intent_payload(
        hook_name="architect-cli",
        target_path=rel_path,
        write_intent="create" if before_hash is None else "overwrite",
        content_hash_before=before_hash,
    )
    decision = await run_hook_chain(payload, hooks=hooks, journal_path=journal_path)
    if decision.decision != "allow":
        raise WorkflowError(
            "pre-write hook rejected architect artifact write",
            details={"hook": decision.hook_name, "reason": decision.reason, "path": rel_path},
        )

    atomic_write(target_path, output_text)
    after = content_hash(output_text)

    seq_aw = await allocate_seq(journal_path)
    await journal_append(
        make_journal_entry(
            seq=seq_aw,
            ts=now_ts(),
            kind="artifact_written",
            target_id=rel_path,
            payload={"slash_command": slash_cmd, "phase": 2, "specialist": specialist_name},
            after_hash=after,
            actor="cli",
        ),
        journal_path,
    )
    return output_text
