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
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sdlc.errors import DispatchError

_WIN_MSG = (
    "sdlc.telemetry.runs.record_agent_run is POSIX-only — file_lock requires"
    " fcntl semantics (Architecture §573)."
)


@dataclass(frozen=True)
class _AgentRunLine:
    """Private placeholder for a single agent_runs.jsonl row (AC9, NOT a wire-format contract).

    Full schema lock arrives in Epic 2B Story 2B.1.
    """

    schema_version: int
    run_id: str
    ts: str
    workflow_step: str
    specialist_name: str
    target_kind: Literal["primary", "parallel", "synthesizer"]
    outcome: Literal["success", "failed"]
    attempts: int
    tokens_in: int
    tokens_out: int
    target_path: str
    duration_ms: int

    def to_json_line(self) -> str:
        """Serialize to a canonical sorted-keys JSON line (no trailing newline)."""
        return json.dumps(
            {
                "schema_version": self.schema_version,
                "run_id": self.run_id,
                "ts": self.ts,
                "workflow_step": self.workflow_step,
                "specialist_name": self.specialist_name,
                "target_kind": self.target_kind,
                "outcome": self.outcome,
                "attempts": self.attempts,
                "tokens_in": self.tokens_in,
                "tokens_out": self.tokens_out,
                "target_path": self.target_path,
                "duration_ms": self.duration_ms,
            },
            sort_keys=True,
            separators=(",", ":"),
        )


def _validate_fields(
    target_kind: str,
    outcome: str,
) -> None:
    """Validate enumerated fields; raises DispatchError on invalid values."""
    valid_kinds = frozenset({"primary", "parallel", "synthesizer"})
    valid_outcomes = frozenset({"success", "failed"})
    if target_kind not in valid_kinds:
        raise DispatchError(
            f"invalid target_kind {target_kind!r}: must be one of {sorted(valid_kinds)}",
            details={"target_kind": target_kind},
        )
    if outcome not in valid_outcomes:
        raise DispatchError(
            f"invalid outcome {outcome!r}: must be one of {sorted(valid_outcomes)}",
            details={"outcome": outcome},
        )


if sys.platform != "win32":
    import asyncio

    from sdlc.concurrency import file_lock as _file_lock

    def _lock_path_for(runs_path: Path) -> Path:
        return Path(str(runs_path) + ".lock")

    async def record_agent_run(
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
        """Append one ``_AgentRunLine`` row to ``runs_path`` (POSIX only).

        Uses ``O_APPEND`` + ``file_lock`` for concurrent serialization (mirrors
        ``journal/writer.py``). Raises ``DispatchError`` on invalid field values.
        """
        _validate_fields(target_kind, outcome)
        line = _AgentRunLine(
            schema_version=1,
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
        )
        json_line = line.to_json_line() + "\n"
        encoded = json_line.encode("utf-8")

        async def _write() -> None:
            runs_path.parent.mkdir(parents=True, exist_ok=True)
            import os

            fd = os.open(str(runs_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
            try:
                os.write(fd, encoded)
                os.fsync(fd)
            finally:
                os.close(fd)

        async with _file_lock(_lock_path_for(runs_path)):
            await asyncio.to_thread(_write)

else:
    async def record_agent_run(  # type: ignore[misc]
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
        """Windows stub — raises DispatchError (POSIX-only operation)."""
        raise DispatchError(
            _WIN_MSG,
            details={"runs_path": str(runs_path), "step": "windows_unsupported"},
        )


__all__ = ["record_agent_run"]
