"""UX-designer dispatch pipeline — extracted from cli/ux.py for LOC cap (Story 2A.13 D2).

Holds parsing, materialization, dispatch + per-file write logic. :mod:`sdlc.cli.ux`
retains pre-flight + error-code mapping only — mirrors the sibling pattern in
:mod:`sdlc.cli._epics_pipeline` and :mod:`sdlc.cli._stories_pipeline`.

Patches applied during code review (2026-05-14):
- P1: reject ``00-`` reserved prefix that collides with phantom anchor filename
- P3: catch ValueError around ``relative_to(root)`` for symlink-escape paths
- P4: reject duplicate filenames in specialist JSON response
- P5: explicit ``isinstance(filename, str)`` / ``isinstance(content, str)`` checks
- P6: explicit ``isinstance(output_text, str)`` check before ``json.loads``
- P7: narrowed ``except`` on ``_materialize_ux_mock_fixture`` registry lookup
- P9: UTF-8 byte length cap on filename (≤ 100 bytes)
- P17: pass ``content_hash_before`` on existing-file overwrite (retry / replan path)
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from types import MappingProxyType
from typing import Final

import typer

from sdlc.cli._runtime_selection import merge_observer_mock_audit
from sdlc.cli.output import emit_error
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
    phase1_prompt_builder,
)
from sdlc.errors import WorkflowError
from sdlc.hooks.payload import build_write_intent_payload
from sdlc.hooks.runner import HookDecision, run_hook_chain
from sdlc.journal import append as journal_append
from sdlc.runtime.abc import AIRuntime
from sdlc.specialists import SpecialistRegistry

_SLASH_CMD: Final[str] = "/sdlc-ux"
_SPECIALIST: Final[str] = "ux-designer"
_ANCHOR_FILENAME: Final[str] = "00-ux-dispatch-anchor.md"
_MAX_FILENAME_BYTES: Final[int] = 100  # P9 — safely under POSIX NAME_MAX=255

# Safe filename: NN-name.md (digit prefix, alnum/hyphens, .md suffix). P1 rejects
# the ``00-`` prefix explicitly below (not via regex) to keep the message
# distinct.  PB7 (review-B): ``re.ASCII`` flag so ``\d`` matches ONLY ASCII
# ``[0-9]`` and does not accept Unicode digit codepoints (e.g. Arabic-Indic
# digits U+0660..U+0669 or fullwidth digits U+FF10..U+FF19) that would bypass
# the ASCII ``startswith("00-")`` check on the line below.
_SAFE_FILENAME_RE: Final[re.Pattern[str]] = re.compile(
    r"^\d{2}-[a-zA-Z0-9][a-zA-Z0-9\-]*\.md$", re.ASCII
)


def validate_ux_filename(filename: str, *, ctx: typer.Context) -> None:
    """Validate specialist-returned filename for safety (AC5 + P1/P9)."""
    # PC5 (review-C): split path-traversal (``/``, ``\``, leading ``../``) from
    # in-name double-dot (innocent ``01-a..b.md`` that the regex rejects anyway)
    # so the error message is not misleading.
    if "/" in filename or "\\" in filename or filename.startswith(".."):
        emit_error(
            "ERR_UNSAFE_FILENAME",
            f"specialist returned unsafe filename (path traversal): {filename!r}",
            ctx=ctx,
            details={"filename": filename, "reason": "path-traversal"},
        )
    if not _SAFE_FILENAME_RE.match(filename):
        emit_error(
            "ERR_UNSAFE_FILENAME",
            f"specialist returned filename not matching NN-name.md pattern: {filename!r}",
            ctx=ctx,
            details={"filename": filename},
        )
    # P1: ``00-*`` is reserved for the dispatch anchor path; reject explicitly so
    # a specialist can't shadow internal scaffolding via a legal-looking name.
    if filename.startswith("00-") or filename == _ANCHOR_FILENAME:
        emit_error(
            "ERR_UNSAFE_FILENAME",
            f"specialist returned reserved filename (00- prefix is reserved): {filename!r}",
            ctx=ctx,
            details={"filename": filename, "reason": "reserved-anchor-prefix"},
        )
    # P9: cap UTF-8 byte length safely under POSIX NAME_MAX.
    if len(filename.encode("utf-8")) > _MAX_FILENAME_BYTES:
        emit_error(
            "ERR_UNSAFE_FILENAME",
            f"specialist returned filename exceeding {_MAX_FILENAME_BYTES} bytes: {filename!r}",
            ctx=ctx,
            details={"filename": filename, "max_bytes": _MAX_FILENAME_BYTES},
        )


def _relative_to_root(path: Path, root: Path, *, ctx: typer.Context) -> str:
    """Return POSIX-relative path of ``path`` under ``root``; emit_error if it escapes (P3)."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        emit_error(
            "ERR_UNSAFE_PATH",
            f"UX artifact path escapes repo root: {path}",
            ctx=ctx,
            details={"path": str(path), "root": str(root)},
        )
        raise  # unreachable — emit_error raises typer.Exit


async def ux_dispatch_and_write_async(  # noqa: C901, PLR0915
    *,
    spec: WorkflowSpec,
    root: Path,
    journal_path: Path,
    agent_runs_path: Path,
    product_text: str,
    ux_dir: Path,
    runtime: AIRuntime,
    registry: SpecialistRegistry,
    hooks: tuple[Callable[[HookPayload], HookDecision], ...],
    ctx: typer.Context,
    allow_mock_invoked: bool = False,
) -> list[dict[str, str]]:
    """Dispatch ux-designer, parse JSON array, write files. Returns [{path, hash}, ...]."""
    from sdlc.specialists.frontmatter import Specialist

    anchor = ux_dir / _ANCHOR_FILENAME
    anchor_rel = _relative_to_root(anchor, root, ctx=ctx)

    def _prompt_builder(sp: object, wf: WorkflowSpec) -> str:
        assert isinstance(sp, Specialist)
        return phase1_prompt_builder(
            sp,
            wf,
            idea_text=product_text,
            role="primary",
            upstream_outputs=(),
        )

    # AC6: write agent_dispatched at CLI layer so the entry exists even when
    # dispatch is mocked in unit tests (emit_agent_dispatched=False below).
    seq_ad = await allocate_seq(journal_path)
    await journal_append(
        make_journal_entry(
            seq=seq_ad,
            ts=now_ts(),
            kind="agent_dispatched",
            target_id=anchor_rel,
            payload={
                "slash_command": _SLASH_CMD,
                "phase": 2,
                "specialist": _SPECIALIST,
            },
            actor="cli",
        ),
        journal_path,
    )

    observer_ctx: dict[str, object] = {}
    merge_observer_mock_audit(observer_ctx, allow_mock_invoked=allow_mock_invoked)
    observer = PanelObserver(
        slash_command=_SLASH_CMD,
        idea_text=product_text,
        extra_context=MappingProxyType(observer_ctx),
        emit_agent_dispatched=False,  # written explicitly above
    )
    result = await dispatch(
        spec,
        runtime=runtime,
        registry=registry,
        repo_root=root,
        journal_path=journal_path,
        agent_runs_path=agent_runs_path,
        prompt_builder=_prompt_builder,
        hooks=hooks,
        observer=observer,
        persist_artifact=False,
        target_path_override=anchor,
    )

    if result.outcome != "success":
        raise WorkflowError(
            f"ux dispatch finished with outcome={result.outcome!r}",
            details={"outcome": result.outcome},
        )

    # P6: explicit isinstance check before json.loads — output_text=None/bytes
    # raises TypeError which is not in the except tuple below.
    output_text = result.agent_result.output_text
    if not isinstance(output_text, str):
        raise WorkflowError(
            "specialist agent_result.output_text must be a string",
            details={"actual_type": type(output_text).__name__},
        )

    try:
        files: object = json.loads(output_text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise WorkflowError(
            "specialist response is not valid JSON",
            details={"cause": str(exc)},
        ) from exc

    if not isinstance(files, list):
        raise WorkflowError(
            "specialist response must be a JSON array",
            details={"type": type(files).__name__},
        )

    artifacts: list[dict[str, str]] = []
    # P4 + PB8 (review-B): case-insensitive duplicate-filename guard. macOS APFS
    # and Windows NTFS/exFAT default to case-insensitive filesystems, so a
    # specialist returning both ``01-Tokens.md`` and ``01-tokens.md`` would
    # silently clobber on disk without this lowercase normalization.
    seen: set[str] = set()
    for entry in files:
        if not isinstance(entry, dict) or "filename" not in entry or "content" not in entry:
            raise WorkflowError(
                "each specialist response entry must have filename + content fields",
                details={"entry": str(entry)[:200]},
            )
        # P5: explicit type checks instead of str() coercion (which would turn
        # None into the literal "None" and silently propagate).
        raw_filename = entry["filename"]
        raw_content = entry["content"]
        if not isinstance(raw_filename, str):
            raise WorkflowError(
                "specialist entry 'filename' must be a string",
                details={"actual_type": type(raw_filename).__name__},
            )
        if not isinstance(raw_content, str):
            raise WorkflowError(
                "specialist entry 'content' must be a string",
                details={"actual_type": type(raw_content).__name__},
            )
        filename = raw_filename
        file_content = raw_content

        validate_ux_filename(filename, ctx=ctx)

        # P4 + PB8 (review-B): reject duplicate filenames using case-insensitive
        # comparison so the second write doesn't silently clobber the first on
        # case-insensitive filesystems.
        canonical = filename.lower()
        if canonical in seen:
            raise WorkflowError(
                "specialist response contains duplicate filename",
                details={"filename": filename},
            )
        seen.add(canonical)

        target = ux_dir / filename
        rel = _relative_to_root(target, root, ctx=ctx)

        # P17: pass content_hash_before when the target file already exists so
        # the hook chain can distinguish create vs overwrite (retry/replan path).
        before_hash: str | None = None
        if target.exists():
            try:
                before_hash = content_hash(target.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                before_hash = None  # fall back to create-semantics on unreadable

        payload = build_write_intent_payload(
            hook_name="ux-cli",
            target_path=rel,
            write_intent="create" if before_hash is None else "overwrite",
            content_hash_before=before_hash,
        )
        decision = await run_hook_chain(payload, hooks=hooks, journal_path=journal_path)
        if decision.decision != "allow":
            raise WorkflowError(
                "pre-write hook rejected UX artifact write",
                details={
                    "hook": decision.hook_name,
                    "reason": decision.reason,
                    "path": rel,
                },
            )

        atomic_write(target, file_content)
        after = content_hash(file_content)

        seq_aw = await allocate_seq(journal_path)
        await journal_append(
            make_journal_entry(
                seq=seq_aw,
                ts=now_ts(),
                kind="artifact_written",
                target_id=rel,
                payload={
                    "slash_command": _SLASH_CMD,
                    "phase": 2,
                    "specialist": _SPECIALIST,
                },
                after_hash=after,
                actor="cli",
            ),
            journal_path,
        )
        artifacts.append({"path": rel, "hash": after})

    return artifacts


def materialize_ux_mock_fixture(
    dest_dir: Path,
    *,
    spec: WorkflowSpec,
    registry: SpecialistRegistry,
    product_text: str,
) -> None:
    """Write a MockAIRuntime fixture for the ux-designer specialist."""
    import yaml

    from sdlc.errors import SpecialistError
    from sdlc.runtime.mock import compute_prompt_hash
    from sdlc.specialists.frontmatter import Specialist

    # P7 (review-A) + PB3 (review-B): narrow except AND re-raise as
    # ``WorkflowError`` so the root cause (missing specialist registration)
    # surfaces immediately at the call site instead of being hidden as a
    # downstream ``MockMissError``. The caller wraps this as
    # ``ERR_UX_DISPATCH_FAILED`` with the specialist name in details.
    try:
        sp = registry.get(_SPECIALIST)
    except (KeyError, SpecialistError) as exc:
        raise WorkflowError(
            f"ux-designer specialist not registered (cannot materialise mock fixture): {exc}",
            details={"specialist": _SPECIALIST, "cause": str(exc)},
        ) from exc
    assert isinstance(sp, Specialist)
    prompt = phase1_prompt_builder(
        sp, spec, idea_text=product_text, role="primary", upstream_outputs=()
    )
    h = compute_prompt_hash(prompt)
    _ph = "**PLACEHOLDER** — MockAIRuntime v1. Real content lands in Story 2B.9.\n"
    placeholder_body = json.dumps(
        [
            {"filename": "01-tokens.md", "content": f"# Design Tokens\n\n{_ph}"},
            {"filename": "02-flows.md", "content": f"# User Flows\n\n{_ph}"},
            {"filename": "03-screens.md", "content": f"# Screen Specs\n\n{_ph}"},
        ]
    )
    records = {
        h: {"output_text": placeholder_body, "tokens_in": 1, "tokens_out": 1, "tool_calls": []}
    }
    atomic_write(
        dest_dir / f"{spec.name}.yaml",
        yaml.safe_dump(records, sort_keys=True, allow_unicode=True),
    )
