"""AgentRun telemetry writer — appends JSONL lines to ``agent_runs.jsonl`` (E3, NFR-OBS-2).

Architecture §888-§892, §1066; ADR-024, ADR-026.

``_AgentRunLine`` is a private internal model, not a frozen wire-format contract.
Per ADR-029 §4 (divergence #4) and Story 2B.1 AC5/D2 it is intentionally kept
private — ``schema_version`` is carried as an in-band field, not an ADR-024
``tests/contract_snapshots/v1/`` snapshot — and the format may still evolve
without an ADR-024 ceremony.

Boundary: ``telemetry/`` depends on ``errors``, ``contracts``, ``journal``,
``concurrency``. Forbidden from ``engine``, ``dispatcher``, ``runtime``, ``cli``.

P15: input validation (attempts, tokens, duration, non-empty strings) added.
P16: lock-path collision fix (use ``Path(str(p) + ".lock")`` instead of ``with_suffix``).
P23: shared serialization helper (eliminate POSIX/Win32 duplication).
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

_VALID_OUTCOMES: frozenset[str] = frozenset({"success", "failed"})
_VALID_TARGET_KINDS: frozenset[str] = frozenset({"primary", "parallel", "synthesizer"})


@dataclass(frozen=True)
class _AgentRunLine:
    schema_version: int
    attempts: int
    duration_ms: int
    outcome: str
    run_id: str
    specialist_name: str
    target_kind: str
    target_path: str
    tokens_in: int
    tokens_out: int
    ts: str
    workflow_step: str
    mock: bool = False
    dispatch_prompt: str | None = None

    def to_json_line(self) -> str:
        d = asdict(self)
        if d.get("dispatch_prompt") is None:
            d.pop("dispatch_prompt", None)
        return json.dumps(d, sort_keys=True) + "\n"


def _validate(  # noqa: C901 — flat field validators; refactoring would obscure
    *,
    outcome: str,
    target_kind: str,
    attempts: int,
    tokens_in: int,
    tokens_out: int,
    duration_ms: int,
    run_id: str,
    workflow_step: str,
    specialist_name: str,
    target_path: str,
) -> None:
    """Validate every AgentRun field before serialization (P15)."""
    if outcome not in _VALID_OUTCOMES:
        raise ValueError(f"Invalid outcome {outcome!r}; must be one of {sorted(_VALID_OUTCOMES)}")
    if target_kind not in _VALID_TARGET_KINDS:
        raise ValueError(
            f"Invalid target_kind {target_kind!r}; must be one of {sorted(_VALID_TARGET_KINDS)}"
        )
    if attempts < 1:
        raise ValueError(f"attempts must be >= 1, got {attempts}")
    if tokens_in < 0:
        raise ValueError(f"tokens_in must be >= 0, got {tokens_in}")
    if tokens_out < 0:
        raise ValueError(f"tokens_out must be >= 0, got {tokens_out}")
    if duration_ms < 0:
        raise ValueError(f"duration_ms must be >= 0, got {duration_ms}")
    for field_name, value in (
        ("run_id", run_id),
        ("workflow_step", workflow_step),
        ("specialist_name", specialist_name),
        ("target_path", target_path),
    ):
        if not value:
            raise ValueError(f"{field_name} must be non-empty")


def _build_line(
    *,
    run_id: str,
    ts: str,
    workflow_step: str,
    specialist_name: str,
    target_kind: str,
    outcome: str,
    attempts: int,
    tokens_in: int,
    tokens_out: int,
    target_path: str,
    duration_ms: int,
    mock: bool = False,
    dispatch_prompt: str | None = None,
) -> str:
    return _AgentRunLine(
        schema_version=1,
        attempts=attempts,
        duration_ms=duration_ms,
        outcome=outcome,
        run_id=run_id,
        specialist_name=specialist_name,
        target_kind=target_kind,
        target_path=target_path,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        ts=ts,
        workflow_step=workflow_step,
        mock=mock,
        dispatch_prompt=dispatch_prompt,
    ).to_json_line()


def _ensure_parent_dir(runs_path: Path) -> None:
    """P15: create parent dir if missing (production paths sometimes start fresh)."""
    runs_path.parent.mkdir(parents=True, exist_ok=True)


def _lock_path_for(runs_path: Path) -> Path:
    """P16: append literal '.lock' so ``agent_runs`` and ``agent_runs.jsonl`` get distinct locks."""
    return Path(str(runs_path) + ".lock")


if sys.platform != "win32":
    from sdlc.concurrency.locks import file_lock

    def record_agent_run(
        runs_path: Path,
        *,
        run_id: str,
        ts: str,
        workflow_step: str,
        specialist_name: str,
        target_kind: Literal["primary", "parallel", "synthesizer"],
        outcome: Literal["success", "failed"],
        attempts: int,
        tokens_in: int,
        tokens_out: int,
        target_path: str,
        duration_ms: int,
        mock: bool = False,
        dispatch_prompt: str | None = None,
    ) -> None:
        """Append one JSONL line to ``runs_path`` under ``file_lock`` (POSIX).

        Serializes concurrent dispatch appends across parallel panel members.
        Caller (dispatcher) wraps this in ``asyncio.to_thread`` so the flock
        acquisition does not block the event loop.
        """
        _validate(
            outcome=outcome,
            target_kind=target_kind,
            attempts=attempts,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            duration_ms=duration_ms,
            run_id=run_id,
            workflow_step=workflow_step,
            specialist_name=specialist_name,
            target_path=target_path,
        )
        line = _build_line(
            run_id=run_id,
            ts=ts,
            workflow_step=workflow_step,
            specialist_name=specialist_name,
            target_kind=target_kind,
            outcome=outcome,
            attempts=attempts,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            target_path=target_path,
            duration_ms=duration_ms,
            mock=mock,
            dispatch_prompt=dispatch_prompt,
        )
        _ensure_parent_dir(runs_path)
        with file_lock(_lock_path_for(runs_path)), runs_path.open("a", encoding="utf-8") as fh:
            fh.write(line)

else:
    # Windows: write without file_lock — see EPIC-2A-DEBT-WIN32-RUNS-LOCK in deferred-work.md.
    # Concurrent panel dispatch on Windows is also gated by journal/writer.py being
    # POSIX-only (raises JournalError), so this code path is in practice unreachable for
    # parallel panels in v1; single-write production-path callers function correctly.
    def record_agent_run(
        runs_path: Path,
        *,
        run_id: str,
        ts: str,
        workflow_step: str,
        specialist_name: str,
        target_kind: Literal["primary", "parallel", "synthesizer"],
        outcome: Literal["success", "failed"],
        attempts: int,
        tokens_in: int,
        tokens_out: int,
        target_path: str,
        duration_ms: int,
        mock: bool = False,
        dispatch_prompt: str | None = None,
    ) -> None:
        """Append one JSONL line to ``runs_path`` (Windows — no file_lock)."""
        _validate(
            outcome=outcome,
            target_kind=target_kind,
            attempts=attempts,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            duration_ms=duration_ms,
            run_id=run_id,
            workflow_step=workflow_step,
            specialist_name=specialist_name,
            target_path=target_path,
        )
        line = _build_line(
            run_id=run_id,
            ts=ts,
            workflow_step=workflow_step,
            specialist_name=specialist_name,
            target_kind=target_kind,
            outcome=outcome,
            attempts=attempts,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            target_path=target_path,
            duration_ms=duration_ms,
            mock=mock,
            dispatch_prompt=dispatch_prompt,
        )
        _ensure_parent_dir(runs_path)
        with runs_path.open("a", encoding="utf-8") as fh:
            fh.write(line)


__all__: tuple[str, ...] = ("record_agent_run",)
