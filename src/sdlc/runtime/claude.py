"""ClaudeAIRuntime — real Claude Code subprocess dispatch (Story 2B.1, FR29)."""

from __future__ import annotations

import asyncio
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
    text = raw if len(raw) <= limit else raw[:limit]
    return text.replace("\n", "\\n")


def _signal_from_returncode(returncode: int) -> int | None:
    if returncode < 0:
        return -returncode
    return None


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
    result_raw = data.get("result", "")
    output_text = str(result_raw) if not isinstance(result_raw, str) else result_raw
    usage_raw = data.get("usage")
    usage: Mapping[str, object] = usage_raw if isinstance(usage_raw, dict) else {}
    tokens_in_raw = usage.get("input_tokens", 0)
    tokens_out_raw = usage.get("output_tokens", 0)
    if not isinstance(tokens_in_raw, int) or not isinstance(tokens_out_raw, int):
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
    """Run ``claude -p --output-format json`` with prompt on stdin."""
    cmd = [claude_bin, "-p", "--output-format", "json"]
    env = os.environ.copy()
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        try:
            stdout, stderr = proc.communicate(input=prompt, timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            proc.terminate()
            try:
                proc.wait(timeout=_TERM_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            raise DispatchError(
                f"timeout after {timeout_seconds}s; subprocess terminated",
                details={
                    "stage": "stream",
                    "timeout_seconds": timeout_seconds,
                    "partial_output": (exc.output or "") if isinstance(exc.output, str) else "",
                },
            ) from exc
        returncode = proc.returncode if proc.returncode is not None else 1
        return stdout or "", stderr or "", returncode
    finally:
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
            sig = _signal_from_returncode(returncode)
            stage = "stream" if stdout else "spawn"
            msg = (
                f"subprocess died with signal {sig} at {stage}"
                if sig is not None
                else f"subprocess exited with code {returncode} at {stage}"
            )
            details: dict[str, object] = {
                "stage": stage,
                "returncode": returncode,
                "partial_output": stdout,
            }
            if sig is not None:
                details["signal"] = sig
            if stderr:
                details["stderr"] = stderr
            raise DispatchError(msg, details=details)
        combined = stdout
        if stderr.strip():
            combined = f"{stdout}\n{stderr}"
        try:
            return _parse_claude_stdout(stdout)
        except DispatchError:
            if stderr.strip() and stdout.strip():
                raise DispatchError(
                    f"malformed JSON from claude: {_excerpt(combined)}",
                    details={
                        "stage": "parse",
                        "excerpt": _excerpt(combined),
                        "stdout": _excerpt(stdout),
                        "stderr": _excerpt(stderr),
                    },
                ) from None
            raise


__all__ = (
    "_DEFAULT_TIMEOUT_SECONDS",
    "_TERM_GRACE_SECONDS",
    "ClaudeAIRuntime",
    "_invoke_claude_blocking",
    "_parse_claude_stdout",
)
