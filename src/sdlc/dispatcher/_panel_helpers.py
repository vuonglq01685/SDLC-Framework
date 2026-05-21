"""Private panel-orchestration helpers for dispatcher.core (AC6 LOC discipline, DR2).

Houses ``_run_member`` (single-specialist dispatch), ``_emit_stop_trigger`` (AC5 placeholder),
``_make_journal_entry``, ``_now_ts``, ``_legacy_default_prompt_builder``, and the process-local
monotonic_seq allocator that fixes panel-dispatch journal regression (P1).

Architecture §821-§824, §1067; ADR-013, ADR-014, ADR-016, ADR-024, ADR-026.

# EPIC-2A-DEBT-WRITE-PRIMITIVE: CLOSED 2026-05-21 (prep-sprint C1) — specialist
# artifact write now goes through ``sdlc.concurrency.io_primitives.atomic_write``
# which provides the 7-step POSIX tmp+rename+fsync protocol with EINTR retry.
# See ADR-031.

# EPIC-2A-DEBT-SHARED-TIME: ``_now_ts`` duplicates ``cli/_time.py:now_rfc3339_utc_ms``.
# Boundary §1106 forbids ``cli/`` import here. Deferred to shared-util follow-up.

# v1 monotonic_seq allocator is process-local: dispatcher is single-process per AC1.
# Cross-process journal coordination (Epic 2B + ClaudeAIRuntime) requires a journal
# API like ``append_with_seq_alloc`` — out of 2A.3 scope.

``_legacy_default_prompt_builder`` is deprecated; use
``sdlc.dispatcher.prompts.phase1_prompt_builder`` for Phase-1 flows (Story 2A.8
closed deferred-work W1). Non-Phase-1 dispatch sites retain it pending Stories
2A.13/2A.14 replacement.
"""

from __future__ import annotations

import asyncio
import datetime
import fnmatch
import hashlib
import inspect
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from sdlc.concurrency.io_primitives import atomic_write
from sdlc.contracts.hook_payload import HookPayload
from sdlc.contracts.journal_entry import JournalEntry
from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.dispatcher.retry import with_retries
from sdlc.errors import DispatchError, WorkflowError
from sdlc.hooks.payload import build_write_intent_payload
from sdlc.hooks.runner import BypassRequest, HookDecision, run_hook_chain
from sdlc.journal import append as journal_append
from sdlc.journal._seq import _read_highest_seq
from sdlc.runtime import AgentResult, AIRuntime
from sdlc.specialists.frontmatter import Specialist
from sdlc.specialists.registry import SpecialistRegistry
from sdlc.telemetry.runs import record_agent_run

if TYPE_CHECKING:
    from sdlc.dispatcher import PanelObserver

_ACTOR = "dispatcher"
# Sentinel hash for non-state-mutation journal entries (dispatch_attempt, stop_trigger_raised).
# JournalEntry.after_hash is sha256-pattern non-null (Story 1.7); a real hash is meaningless
# for "attempted dispatch" events. EPIC-2A-DEBT-JOURNAL-NULL-AFTER-HASH tracks lifting this
# constraint for non-mutation kinds (Epic 2B).
_NULL_HASH = "sha256:" + "0" * 64


def _content_hash(text: str) -> str:
    """SHA-256 of an artifact's text payload (used by artifact_written entries)."""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DispatchMemberResult:
    """Result of a single panel-member dispatch (mirrors public DispatchResult shape)."""

    specialist_name: str
    target_path: Path
    agent_result: AgentResult
    attempts: int
    outcome: Literal["success", "failed", "hook_rejected"]


def _now_ts() -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _legacy_default_prompt_builder(specialist: Specialist, step: WorkflowSpec) -> str:
    """Legacy 2-arg prompt — verbatim ``specialist.body`` (Story 2A.3).

    Phase-1 flows use :func:`sdlc.dispatcher.prompts.phase1_prompt_builder` instead
    (Story 2A.8, closes deferred-work W1). Non-Phase-1 dispatch sites keep this until
    Stories 2A.13/2A.14 replace it.
    """
    return specialist.body


def _make_journal_entry(
    *,
    seq: int,
    ts: str,
    kind: str,
    target_id: str,
    payload: dict[str, object],
    after_hash: str = _NULL_HASH,
    actor: str | None = None,
) -> JournalEntry:
    return JournalEntry(
        schema_version=1,
        monotonic_seq=seq,
        ts=ts,
        actor=actor if actor is not None else _ACTOR,
        kind=kind,
        target_id=target_id,
        before_hash=None,
        after_hash=after_hash,
        payload=payload,
    )


# Process-local seq allocator (P1 fix). Per-journal-path async lock + cached "next seq".
# Cache primed from disk on first use; advanced atomically per journal_append call.
# Cross-process correctness requires journal-side allocator (Epic 2B).
_SEQ_LOCKS: dict[Path, asyncio.Lock] = {}
_SEQ_CACHE: dict[Path, int] = {}
_SEQ_REGISTRY_LOCK = asyncio.Lock()


def _journal_seq_cache_key(journal_path: Path) -> Path:
    """Stable process-local cache key for ``_allocate_seq`` / ``_reset_seq_cache_for_test``.

    macOS often surfaces pytest tmp dirs as ``/var/folders/...`` while
    ``Path.resolve()`` yields ``/private/var/folders/...`` for the same inode.
    Using one canonical form prevents duplicate seq caches (and dead
    ``asyncio.Lock`` keys) for the same journal within one process (F3).
    """
    try:
        return journal_path.expanduser().resolve()
    except OSError:
        return journal_path


async def _allocate_seq(journal_path: Path) -> int:
    """Allocate next monotonic_seq for ``journal_path`` (process-local).

    Returns ``max(disk_highest, last_allocated_in_this_process) + 1`` under the
    per-journal async lock so callers stay monotonic even if the cache was
    cleared or diverged from on-disk state (CLI hand-off after ``dispatch``).
    """
    key = _journal_seq_cache_key(journal_path)
    async with _SEQ_REGISTRY_LOCK:
        lock = _SEQ_LOCKS.setdefault(key, asyncio.Lock())
    async with lock:
        disk_highest = await asyncio.to_thread(_read_highest_seq, key)
        cached_high = _SEQ_CACHE.get(key, -1)
        base = max(disk_highest, cached_high)
        nxt = base + 1
        _SEQ_CACHE[key] = nxt
        return nxt


def _reset_seq_cache_for_test(journal_path: Path | None = None) -> None:
    """Test-only hook: reset the process-local seq cache for a path (or all paths)."""
    if journal_path is None:
        _SEQ_CACHE.clear()
        _SEQ_LOCKS.clear()
    else:
        key = _journal_seq_cache_key(journal_path)
        _SEQ_CACHE.pop(key, None)
        _SEQ_LOCKS.pop(key, None)


def _unified_write_target_panel(step: WorkflowSpec) -> bool:
    """True when synthesizer is set and every panel member writes one identical concrete glob.

    Used to skip intermediate disk writes so only the synthesizer persists the artifact
    (Story 2A.8 AC3, Story 2A.3 synthesizer-as-canonical-writer semantics).
    """
    if not step.synthesizer_agent:
        return False
    names: list[str] = [step.primary_agent, *step.parallel_agents, step.synthesizer_agent]
    paths: list[str] = []
    for name in names:
        globs = step.write_globs.get(name)
        if not globs or len(globs) != 1:
            return False
        g0 = globs[0]
        if any(ch in g0 for ch in "*?["):
            return False
        paths.append(g0)
    return len(set(paths)) == 1


def _validate_target_path(repo_root: Path, raw_glob: str) -> Path:
    """Validate write target stays under ``repo_root`` and is concrete (no glob chars). P2 + P3."""
    if any(ch in raw_glob for ch in "*?["):
        raise DispatchError(
            f"write target {raw_glob!r} contains glob characters; expected concrete path (AC8)",
            details={"write_glob": raw_glob},
        )
    target_path = (repo_root / raw_glob).resolve()
    try:
        target_path.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise DispatchError(
            f"write target {raw_glob!r} resolves outside repo_root {repo_root!s}",
            details={"write_glob": raw_glob, "resolved": str(target_path)},
        ) from exc
    return target_path


async def _emit_stop_trigger(
    specialist_name: str,
    step_name: str,
    journal_path: Path,
    *,
    last_error: str | None = None,
) -> None:
    """Append a stop_trigger_raised placeholder entry (AC5, TODO(epic-4))."""
    seq = await _allocate_seq(journal_path)
    payload: dict[str, object] = {
        "trigger": "agent_failure_after_retries",
        "specialist": specialist_name,
        "step": step_name,
        "epic_4_placeholder": True,
    }
    if last_error is not None:
        payload["last_error"] = last_error
    await journal_append(
        _make_journal_entry(
            seq=seq,
            ts=_now_ts(),
            kind="stop_trigger_raised",
            target_id=f"{step_name}/{specialist_name}",
            payload=payload,
        ),
        journal_path,
    )


async def _emit_hook_rejected(
    *,
    step: WorkflowSpec,
    specialist_name: str,
    target_kind: Literal["primary", "parallel", "synthesizer"],
    target_path: Path,
    journal_path: Path,
    decision: HookDecision,
) -> DispatchMemberResult:
    """Append dispatch_attempt(outcome=hook_rejected); skip write (DR4→D1: attempt=0)."""
    seq = await _allocate_seq(journal_path)
    await journal_append(
        _make_journal_entry(
            seq=seq,
            ts=_now_ts(),
            kind="dispatch_attempt",
            target_id=f"{step.name}/{specialist_name}",
            payload={
                "specialist": specialist_name,
                "outcome": "hook_rejected",
                "attempt": 0,
                "target_kind": target_kind,
                "hook_name": decision.hook_name,
                "error_code": decision.error_code,
            },
        ),
        journal_path,
    )
    return DispatchMemberResult(
        specialist_name=specialist_name,
        target_path=target_path,
        agent_result=AgentResult(output_text="", tokens_in=0, tokens_out=0),
        attempts=0,
        outcome="hook_rejected",
    )


async def _run_pre_write_hooks(
    hooks: tuple[Callable[[HookPayload], HookDecision], ...],
    target_path: Path,
    repo_root: Path,
    journal_path: Path,
    bypass: BypassRequest | None,
) -> HookDecision | None:
    """Run hook chain before write; return deny decision or None if allowed."""
    if not hooks:
        return None
    # F3: symmetric .resolve() (macOS tmp_path → /private/var/ symlink edge case).
    # P23: a resolved path that escapes ``repo_root`` (e.g. via symlink) is a
    # safety violation — never silently fall back to an absolute path.
    try:
        rel_target = target_path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise WorkflowError(
            "artifact path escapes repository root",
            details={
                "target_path": str(target_path),
                "repo_root": str(repo_root),
                "resolved": str(target_path.resolve()),
            },
        ) from exc
    hook_payload = build_write_intent_payload(
        hook_name="pre_write",
        target_path=rel_target,
        write_intent="dispatcher_artifact_write",
    )
    decision = await run_hook_chain(
        hook_payload,
        hooks=hooks,
        journal_path=journal_path,
        bypass_phase_gate=bypass.bypass_phase_gate if bypass else False,
        justification=bypass.justification if bypass else None,
    )
    return decision if decision.decision == "deny" else None


def _globstar_match(path: str, pattern: str) -> bool:
    """Match a POSIX path against a glob pattern with ``**`` support.

    Story 2A.10 review P8 — validates ``target_path_override`` against the
    workflow's ``write_globs``. ``**`` matches zero or more path segments;
    ``*``/``?``/character-class metacharacters match within a single
    segment (delegated to :mod:`fnmatch`). Segment-aware so ``*.md`` does
    NOT cross ``/`` boundaries (Python's bare ``fnmatch`` does and would
    over-accept).
    """
    return _match_segments(path.split("/"), pattern.split("/"))


def _match_segments(path_parts: list[str], pat_parts: list[str]) -> bool:
    if not pat_parts:
        return not path_parts
    head = pat_parts[0]
    if head == "**":
        for i in range(len(path_parts) + 1):
            if _match_segments(path_parts[i:], pat_parts[1:]):
                return True
        return False
    if not path_parts:
        return False
    if fnmatch.fnmatchcase(path_parts[0], head):
        return _match_segments(path_parts[1:], pat_parts[1:])
    return False


def _is_phase1_prompt_builder(prompt_builder: Callable[..., str]) -> bool:
    """True if ``prompt_builder`` accepts the Phase-1 kw-only args (idea_text, role, ...).

    Used by ``_run_member`` to pick the right call shape without an explicit flag.
    Legacy 2-arg ``_legacy_default_prompt_builder`` returns False; Phase-1
    ``phase1_prompt_builder`` returns True.
    """
    try:
        sig = inspect.signature(prompt_builder)
    except (TypeError, ValueError):
        return False
    return "idea_text" in sig.parameters and "role" in sig.parameters


async def _run_member(  # noqa: C901, PLR0912, PLR0915 — panel member orchestration; split deferred
    step: WorkflowSpec,
    specialist_name: str,
    target_kind: Literal["primary", "parallel", "synthesizer"],
    *,
    runtime: AIRuntime,
    registry: SpecialistRegistry,
    repo_root: Path,
    journal_path: Path,
    agent_runs_path: Path,
    prompt_builder: Callable[..., str],
    sleep: Callable[[float], Awaitable[None]],
    max_attempts: int,
    extra_context: dict[str, object] | None = None,
    extra_journal_payload: dict[str, object] | None = None,
    target_path_override: Path | None = None,
    hooks: tuple[Callable[[HookPayload], HookDecision], ...] = (),
    bypass: BypassRequest | None = None,
    observer: PanelObserver | None = None,
    upstream_outputs: tuple[str, ...] = (),
    persist_artifact: bool = True,
) -> DispatchMemberResult:
    """Dispatch a single specialist as a panel member (primary/parallel/synthesizer).

    Story 2A.8 D1-C: CLI-specific concerns (slash_command, idea_text passthrough,
    journal-emit gating, frontmatter context) are read from ``observer``. When
    ``observer is None`` we behave as if ``emit_agent_dispatched=False`` and use
    empty strings/mappings for the passthrough fields.
    """
    specialist = registry.get(specialist_name)

    if target_path_override is not None:
        target_path = target_path_override
    else:
        write_globs = step.write_globs.get(specialist_name)
        if not write_globs:
            raise DispatchError(
                f"workflow step {step.name!r} has no write_globs entry for specialist"
                f" {specialist_name!r}",
                details={"step": step.name, "specialist": specialist_name},
            )
        target_path = _validate_target_path(repo_root, write_globs[0])
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # P23: escaping repo_root via the resolved path is a safety violation —
    # raise instead of writing an absolute path into the journal.
    try:
        rel_for_journal = target_path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise WorkflowError(
            "artifact path escapes repository root",
            details={
                "target_path": str(target_path),
                "repo_root": str(repo_root),
                "resolved": str(target_path.resolve()),
                "specialist": specialist_name,
            },
        ) from exc

    idea_text: str = "" if observer is None or observer.idea_text is None else observer.idea_text
    slash_command: str | None = None if observer is None else observer.slash_command
    emit_agent_dispatched: bool = False if observer is None else observer.emit_agent_dispatched
    observer_extra_context: dict[str, object] = (
        {} if observer is None else dict(observer.extra_context)
    )

    if _is_phase1_prompt_builder(prompt_builder):
        builder_kwargs: dict[str, Any] = {
            "idea_text": idea_text,
            "role": target_kind,
            "upstream_outputs": upstream_outputs,
        }
        # Forward observer.extra_context only for the synthesizer; non-synth
        # builders use the empty default. D3-A: synthesizer needs frontmatter.
        if target_kind == "synthesizer":
            builder_kwargs["extra_context"] = observer_extra_context
        prompt = prompt_builder(specialist, step, **builder_kwargs)
    else:
        prompt = prompt_builder(specialist, step)

    if emit_agent_dispatched and slash_command:
        # P22: emit ``agent_dispatched`` ONCE per agent (not per attempt) and
        # omit the ``attempt`` field — per-attempt accounting lives on
        # ``dispatch_attempt`` entries. ``agent_dispatched`` marks the
        # provenance of who was assigned to write the target, not retry count.
        seq_ad = await _allocate_seq(journal_path)
        idea_hash = "sha256:" + hashlib.sha256(idea_text.encode("utf-8")).hexdigest()
        ad_payload: dict[str, object] = {
            "slash_command": slash_command,
            "specialist": specialist_name,
            "role": target_kind,
            "idea_hash": idea_hash,
        }
        # P12 (code review): protect canonical keys from caller-supplied extras —
        # a misconfigured caller could pass ``{"specialist": "evil"}`` and clobber
        # the actor field, corrupting the audit log. Reject collisions explicitly.
        _CANONICAL_AD_KEYS: frozenset[str] = frozenset(ad_payload)
        extras_src = observer_extra_context.get("agent_dispatched_extras")
        if isinstance(extras_src, Mapping):
            for k, v in extras_src.items():
                key = str(k)
                if key in _CANONICAL_AD_KEYS:
                    raise ValueError(
                        f"agent_dispatched_extras key {key!r} collides with a "
                        f"canonical agent_dispatched payload key"
                    )
                ad_payload[key] = v
        await journal_append(
            _make_journal_entry(
                seq=seq_ad,
                ts=_now_ts(),
                kind="agent_dispatched",
                target_id=rel_for_journal,
                actor=f"agent:{specialist_name}",
                payload=ad_payload,
            ),
            journal_path,
        )

    context: dict[str, object] = {
        "workflow_step": step.name,
        "agent_name": specialist_name,
        "target_kind": target_kind,
    }
    if extra_context:
        context.update(extra_context)

    actual_attempts = 0

    async def _on_attempt(attempt_num: int, outcome: str) -> None:
        nonlocal actual_attempts
        actual_attempts = attempt_num
        seq = await _allocate_seq(journal_path)
        attempt_payload: dict[str, object] = {
            "specialist": specialist_name,
            "outcome": outcome,
            "attempt": attempt_num,
            "target_kind": target_kind,
        }
        if extra_journal_payload:
            attempt_payload.update(extra_journal_payload)
        await journal_append(
            _make_journal_entry(
                seq=seq,
                ts=_now_ts(),
                kind="dispatch_attempt",
                target_id=f"{step.name}/{specialist_name}",
                payload=attempt_payload,
            ),
            journal_path,
        )

    deny = await _run_pre_write_hooks(hooks, target_path, repo_root, journal_path, bypass)
    if deny is not None:
        return await _emit_hook_rejected(
            step=step,
            specialist_name=specialist_name,
            target_kind=target_kind,
            target_path=target_path,
            journal_path=journal_path,
            decision=deny,
        )

    t_start = time.monotonic()
    try:
        agent_result: AgentResult = await with_retries(
            lambda: runtime.dispatch(prompt, context),
            max_attempts=max_attempts,
            sleep=sleep,
            on_attempt=_on_attempt,
        )
    except DispatchError as exc:
        details = dict(exc.details) if exc.details else {}
        details["specialist"] = specialist_name
        details["step"] = step.name
        raise DispatchError(str(exc), details=details) from exc

    duration_ms = int((time.monotonic() - t_start) * 1000)
    ts = _now_ts()
    run_id = str(uuid.uuid4())
    rel_target = rel_for_journal

    if not persist_artifact:
        await asyncio.to_thread(
            record_agent_run,
            agent_runs_path,
            run_id=run_id,
            ts=ts,
            workflow_step=step.name,
            specialist_name=specialist_name,
            target_kind=target_kind,
            outcome="success",
            attempts=actual_attempts or 1,
            tokens_in=agent_result.tokens_in,
            tokens_out=agent_result.tokens_out,
            target_path=rel_target,
            duration_ms=duration_ms,
            dispatch_prompt=prompt,
        )
        return DispatchMemberResult(
            specialist_name=specialist_name,
            target_path=target_path,
            agent_result=agent_result,
            attempts=actual_attempts or 1,
            outcome="success",
        )

    atomic_write(target_path, agent_result.output_text)

    artifact_seq = await _allocate_seq(journal_path)
    # D2-B: synthesizer-canonical write — actor reflects the agent that produced
    # the bytes. CLI no longer post-processes the file, so the journal entry MUST
    # name the agent (not 'cli'). When an observer carries a slash_command we
    # include it in the payload for downstream filtering.
    art_payload: dict[str, object] = {
        "target": rel_target,
        "writer": "dispatcher",
        "specialist": specialist_name,
        "run_id": run_id,
    }
    if slash_command:
        art_payload["slash_command"] = slash_command
        art_payload["phase"] = 1
    actor_for_write = f"agent:{specialist_name}"
    await journal_append(
        _make_journal_entry(
            seq=artifact_seq,
            ts=ts,
            kind="artifact_written",
            target_id=rel_target,
            payload=art_payload,
            after_hash=_content_hash(agent_result.output_text),
            actor=actor_for_write,
        ),
        journal_path,
    )

    await asyncio.to_thread(
        record_agent_run,
        agent_runs_path,
        run_id=run_id,
        ts=ts,
        workflow_step=step.name,
        specialist_name=specialist_name,
        target_kind=target_kind,
        outcome="success",
        attempts=actual_attempts or 1,
        tokens_in=agent_result.tokens_in,
        tokens_out=agent_result.tokens_out,
        target_path=rel_target,
        duration_ms=duration_ms,
        dispatch_prompt=prompt,
    )

    return DispatchMemberResult(
        specialist_name=specialist_name,
        target_path=target_path,
        agent_result=agent_result,
        attempts=actual_attempts or 1,
        outcome="success",
    )


__all__: tuple[str, ...] = (
    "DispatchMemberResult",
    "_allocate_seq",
    "_emit_hook_rejected",
    "_emit_stop_trigger",
    "_is_phase1_prompt_builder",
    "_legacy_default_prompt_builder",
    "_make_journal_entry",
    "_now_ts",
    "_reset_seq_cache_for_test",
    "_run_member",
    "_unified_write_target_panel",
    "_validate_target_path",
)
