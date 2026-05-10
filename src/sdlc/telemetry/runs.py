"""AgentRun telemetry writer — appends JSONL lines to ``agent_runs.jsonl`` (E3, NFR-OBS-2).

Architecture §888-§892, §1066; ADR-024, ADR-026.

AgentRun is a 2A placeholder; full wire-format lock arrives in Epic 2B Story 2B.1.
Format may evolve in 2A without ADR-024 ceremony.

Boundary: ``telemetry/`` depends on ``errors``, ``contracts``, ``journal``,
``concurrency``. Forbidden from ``engine``, ``dispatcher``, ``runtime``, ``cli``.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from sdlc.errors import DispatchError

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

    def to_json_line(self) -> str:
        return json.dumps(asdict(self), sort_keys=True) + "\n"


def _validate(outcome: str, target_kind: str) -> None:
    if outcome not in _VALID_OUTCOMES:
        raise ValueError(
            f"Invalid outcome {outcome!r}; must be one of {sorted(_VALID_OUTCOMES)}"
        )
    if target_kind not in _VALID_TARGET_KINDS:
        raise ValueError(
            f"Invalid target_kind {target_kind!r}; must be one of {sorted(_VALID_TARGET_KINDS)}"
        )


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
    ) -> None:
        """Append one JSONL line to ``runs_path`` under ``file_lock`` (POSIX).

        Serializes concurrent dispatch appends across parallel panel members.
        """
        _validate(outcome, target_kind)
        line = _AgentRunLine(
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
        ).to_json_line()
        lock_path = runs_path.with_suffix(".jsonl.lock")
        with file_lock(lock_path):
            with runs_path.open("a", encoding="utf-8") as fh:
                fh.write(line)

else:
    # Windows: write without file_lock (no cross-thread atomicity — concurrent writes
    # are unsafe; the concurrent-write test is marked _SKIP_WIN32). Single-write use
    # cases (unit tests, non-parallel dispatch) function correctly.
    def record_agent_run(  # type: ignore[misc]
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
    ) -> None:
        """Append one JSONL line to ``runs_path`` (Windows — no file_lock)."""
        _validate(outcome, target_kind)
        line = _AgentRunLine(
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
        ).to_json_line()
        with runs_path.open("a", encoding="utf-8") as fh:
            fh.write(line)


__all__: tuple[str, ...] = ("record_agent_run",)
