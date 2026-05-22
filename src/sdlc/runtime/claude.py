"""ClaudeAIRuntime — real Claude Code subprocess dispatch (Story 2B.1, FR29)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import subprocess
from collections.abc import Mapping
from typing import Final

from sdlc.errors import DispatchError
from sdlc.runtime.abc import AgentResult, AIRuntime

_DEFAULT_TIMEOUT_SECONDS: Final[int] = 300
_TERM_GRACE_SECONDS: Final[float] = 5.0
_JSON_EXCERPT_LEN: Final[int] = 200
_CLAUDE_BIN: Final[str] = "claude"


def _excerpt(raw: str, *, limit: int = _JSON_EXCERPT_LEN) -> str:
    """Return a newline-escaped excerpt of ``raw``, capped at ``limit`` characters.

    The cap is applied *after* newline-escaping so the result never exceeds
    ``limit`` even for newline-bearing payloads — the AC3 200-char contract holds
    regardless of how many newlines the offending output contains.
    """
    escaped = raw[:limit].replace("\n", "\\n")
    return escaped[:limit]


def _signal_from_returncode(returncode: int) -> int | None:
    if returncode < 0:
        return -returncode
    return None


def _terminate(proc: subprocess.Popen[str]) -> None:
    """Terminate + reap ``proc``: SIGTERM, grace, SIGKILL — never blocking forever.

    Every ``wait`` is bounded by ``_TERM_GRACE_SECONDS``; even a SIGKILL-unreapable
    child (uninterruptible sleep) costs at most one extra grace period rather than
    hanging the ``asyncio.to_thread`` worker indefinitely.
    """
    proc.terminate()
    try:
        proc.wait(timeout=_TERM_GRACE_SECONDS)
        return
    except subprocess.TimeoutExpired:
        proc.kill()
    with contextlib.suppress(subprocess.TimeoutExpired):
        proc.wait(timeout=_TERM_GRACE_SECONDS)


def _subprocess_failure_error(stdout: str, stderr: str, returncode: int) -> DispatchError:
    """Build the ``DispatchError`` for a non-zero subprocess exit.

    Spawn failures raise ``stage="spawn"`` inside ``_invoke_claude_blocking``, so a
    non-zero exit here is always a process that ran — a ``stream``-stage failure.
    """
    sig = _signal_from_returncode(returncode)
    msg = (
        f"subprocess died with signal {sig} at stream"
        if sig is not None
        else f"subprocess exited with code {returncode} at stream"
    )
    details: dict[str, object] = {
        "stage": "stream",
        "returncode": returncode,
        "partial_output": stdout,
    }
    if sig is not None:
        details["signal"] = sig
    if stderr:
        details["stderr"] = stderr
    return DispatchError(msg, details=details)


def _mixed_stream_parse_error(stdout: str, stderr: str, parse_exc: DispatchError) -> DispatchError:
    """Re-frame a stdout parse failure that also carries stderr content (AC3 case d)."""
    combined = f"{stdout}\n{stderr}"
    details: dict[str, object] = {
        "stage": "parse",
        "excerpt": _excerpt(combined),
        "stdout": _excerpt(stdout),
        "stderr": _excerpt(stderr),
    }
    # Preserve the underlying JSONDecodeError message — the single most useful
    # field for diagnosing truncation vs. an invalid escape.
    inner_error = (parse_exc.details or {}).get("error")
    if inner_error is not None:
        details["error"] = inner_error
    return DispatchError(f"malformed JSON from claude: {_excerpt(combined)}", details=details)


def _parse_claude_stdout(stdout: str) -> AgentResult:
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise DispatchError(
            f"malformed JSON from claude: {_excerpt(stdout)}",
            details={
                "stage": "parse",
                "excerpt": _excerpt(stdout),
                "error": str(exc),
            },
        ) from exc
    if not isinstance(data, dict):
        raise DispatchError(
            f"malformed JSON from claude: {_excerpt(stdout)}",
            details={"stage": "parse", "excerpt": _excerpt(stdout), "shape": type(data).__name__},
        )
    # A claude result envelope explicitly flagged as an error must not be laundered
    # into a successful AgentResult — surface it as a dispatch failure.
    if data.get("is_error") is True:
        raise DispatchError(
            f"claude reported an error result: {_excerpt(stdout)}",
            details={"stage": "parse", "excerpt": _excerpt(stdout), "is_error": True},
        )
    # `result` must be a real string — never str()-coerce a dict / None / number,
    # which would fabricate output_text from an error payload or nested object.
    result_raw = data.get("result")
    if not isinstance(result_raw, str):
        raise DispatchError(
            f"malformed JSON from claude: 'result' is {type(result_raw).__name__}, expected str",
            details={
                "stage": "parse",
                "excerpt": _excerpt(stdout),
                "result_type": type(result_raw).__name__,
            },
        )
    output_text = result_raw
    usage_raw = data.get("usage")
    usage: Mapping[str, object] = usage_raw if isinstance(usage_raw, dict) else {}
    tokens_in_raw = usage.get("input_tokens", 0)
    tokens_out_raw = usage.get("output_tokens", 0)
    # bool is an int subclass; reject it explicitly so AgentResult (strict=True) is
    # never handed a bool, which would raise an uncaught pydantic ValidationError.
    if (
        not isinstance(tokens_in_raw, int)
        or isinstance(tokens_in_raw, bool)
        or not isinstance(tokens_out_raw, int)
        or isinstance(tokens_out_raw, bool)
    ):
        raise DispatchError(
            f"malformed JSON from claude: {_excerpt(stdout)}",
            details={"stage": "parse", "excerpt": _excerpt(stdout)},
        )
    tokens_in = tokens_in_raw
    tokens_out = tokens_out_raw
    if tokens_in < 0 or tokens_out < 0:
        raise DispatchError(
            f"malformed JSON from claude: {_excerpt(stdout)}",
            details={"stage": "parse", "excerpt": _excerpt(stdout)},
        )
    return AgentResult(
        output_text=output_text,
        tool_calls=(),
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        mock=False,
    )


def _invoke_claude_blocking(
    *,
    prompt: str,
    timeout_seconds: int,
    claude_bin: str,
) -> tuple[str, str, int]:
    """Run ``claude -p --output-format json`` with the prompt on stdin.

    Spawn failure (e.g. ``claude`` not installed / not on PATH) is mapped to a
    ``DispatchError`` at the ``spawn`` stage rather than escaping as a raw
    ``FileNotFoundError``. The subprocess is always terminated and reaped — on
    timeout, on any I/O failure, and on the normal-return path — so no orphaned
    ``claude`` child outlives this call.
    """
    cmd = [claude_bin, "-p", "--output-format", "json"]
    env = os.environ.copy()
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
    except OSError as exc:
        raise DispatchError(
            f"failed to spawn claude ({claude_bin!r}): {exc}",
            details={"stage": "spawn", "claude_bin": claude_bin, "error": str(exc)},
        ) from exc
    try:
        try:
            stdout, stderr = proc.communicate(input=prompt, timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            _terminate(proc)
            raise DispatchError(
                f"timeout after {timeout_seconds}s; subprocess terminated",
                details={
                    "stage": "stream",
                    "timeout_seconds": timeout_seconds,
                    "partial_output": (exc.output or "") if isinstance(exc.output, str) else "",
                },
            ) from exc
        except OSError as exc:
            raise DispatchError(
                f"subprocess I/O failed: {exc}",
                details={"stage": "stream", "error": str(exc)},
            ) from exc
        returncode = proc.returncode if proc.returncode is not None else 1
        return stdout or "", stderr or "", returncode
    finally:
        # Guarantee no orphan on every exit path — not just the timeout branch.
        if proc.poll() is None:
            _terminate(proc)
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            if stream is not None:
                stream.close()


class ClaudeAIRuntime(AIRuntime):
    """Real Claude Code runtime via subprocess (Architecture §1120, Story 2B.1)."""

    def __init__(
        self,
        *,
        timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
        claude_bin: str = _CLAUDE_BIN,
    ) -> None:
        if timeout_seconds < 1:
            raise ValueError("timeout_seconds must be >= 1")
        self._timeout_seconds = timeout_seconds
        self._claude_bin = claude_bin

    async def dispatch(self, prompt: str, context: Mapping[str, object]) -> AgentResult:
        del context  # v1 open-ended; formal schema is Story 2A-3
        stdout, stderr, returncode = await asyncio.to_thread(
            _invoke_claude_blocking,
            prompt=prompt,
            timeout_seconds=self._timeout_seconds,
            claude_bin=self._claude_bin,
        )
        if returncode != 0:
            raise _subprocess_failure_error(stdout, stderr, returncode)
        # Exit 0 with no stdout is a distinct failure from malformed JSON — do not
        # let _parse_claude_stdout("") raise a misleading "malformed JSON" error.
        if not stdout.strip():
            raise DispatchError(
                "claude exited 0 but produced no output on stdout",
                details={
                    "stage": "parse",
                    "returncode": returncode,
                    "stderr": _excerpt(stderr),
                },
            )
        try:
            return _parse_claude_stdout(stdout)
        except DispatchError as parse_exc:
            # stdout is non-empty here (guarded above); stderr content alongside a
            # stdout parse failure is the AC3 "stdout mixed with stderr" case.
            if stderr.strip():
                raise _mixed_stream_parse_error(stdout, stderr, parse_exc) from parse_exc
            raise


__all__ = (
    "_DEFAULT_TIMEOUT_SECONDS",
    "_TERM_GRACE_SECONDS",
    "ClaudeAIRuntime",
    "_invoke_claude_blocking",
    "_parse_claude_stdout",
)
