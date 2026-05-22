"""Unit + integration tests for ClaudeAIRuntime (Story 2B.1)."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from sdlc.errors import DispatchError
from sdlc.runtime.abc import AIRuntime
from sdlc.runtime.claude import (
    _TERM_GRACE_SECONDS,
    ClaudeAIRuntime,
    _parse_claude_stdout,
)

_STUBS_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "claude_stubs"


def _install_stub(monkeypatch: pytest.MonkeyPatch, stub_name: str, tmp_path: Path) -> Path:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    target = bindir / "claude"
    shutil.copy(_STUBS_DIR / stub_name, target)
    target.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")
    return target


@pytest.mark.unit
def test_claude_runtime_is_airuntime_subclass() -> None:
    assert issubclass(ClaudeAIRuntime, AIRuntime)
    runtime = ClaudeAIRuntime()
    assert runtime._timeout_seconds >= 1


@pytest.mark.unit
def test_parse_claude_stdout_happy_path() -> None:
    raw = json.dumps(
        {
            "type": "result",
            "result": "hello",
            "usage": {"input_tokens": 5, "output_tokens": 2},
        }
    )
    result = _parse_claude_stdout(raw)
    assert result.output_text == "hello"
    assert result.tokens_in == 5
    assert result.tokens_out == 2
    assert result.mock is False


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "label"),
    [
        ('{"result": "x"', "truncated"),
        ('{"result": "\\u"', "invalid_escape"),
        ("plain text only", "mixed_text"),
    ],
)
def test_parse_claude_stdout_malformed_raises(raw: str, label: str) -> None:
    del label
    with pytest.raises(DispatchError) as ei:
        _parse_claude_stdout(raw)
    assert "malformed JSON from claude" in str(ei.value)
    assert len(str(ei.value.details.get("excerpt", ""))) <= 200


@pytest.mark.unit
def test_parse_claude_stdout_excerpt_caps_multi_kb_payload() -> None:
    raw = "x" * 5000
    with pytest.raises(DispatchError) as ei:
        _parse_claude_stdout(raw)
    excerpt = str(ei.value.details["excerpt"])
    assert len(excerpt) == 200


@pytest.mark.unit
def test_dispatch_happy_path_stub_claude(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """AC7 anti-tautology: deleting parse logic would fail this test."""
    _install_stub(monkeypatch, "claude_ok", tmp_path)
    runtime = ClaudeAIRuntime(timeout_seconds=30)
    result = asyncio.run(runtime.dispatch("prompt-body-xyz", {"workflow_step": "smoke"}))
    assert result.mock is False
    assert result.output_text.startswith("stub-ok:prompt-body-xyz")
    assert result.tokens_in == 11
    assert result.tokens_out == 7


@pytest.mark.unit
def test_dispatch_kill_midstream_preserves_partial_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_stub(monkeypatch, "claude_kill_midstream", tmp_path)
    runtime = ClaudeAIRuntime(timeout_seconds=30)
    with pytest.raises(DispatchError) as ei:
        asyncio.run(runtime.dispatch("x", {"workflow_step": "smoke"}))
    assert "subprocess died with signal" in str(ei.value)
    assert ei.value.details.get("partial_output")
    assert ei.value.details.get("signal") == 9


@pytest.mark.unit
def test_dispatch_malformed_json_from_stub(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_stub(monkeypatch, "claude_malformed_json", tmp_path)
    runtime = ClaudeAIRuntime(timeout_seconds=30)
    with pytest.raises(DispatchError) as ei:
        asyncio.run(runtime.dispatch("x", {"workflow_step": "smoke"}))
    assert "malformed JSON from claude" in str(ei.value)


@pytest.mark.unit
def test_dispatch_stdout_stderr_mixed_malformed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_stub(monkeypatch, "claude_stderr_json", tmp_path)
    runtime = ClaudeAIRuntime(timeout_seconds=30)
    with pytest.raises(DispatchError) as ei:
        asyncio.run(runtime.dispatch("x", {"workflow_step": "smoke"}))
    assert "malformed JSON from claude" in str(ei.value)


@pytest.mark.integration
def test_dispatch_timeout_terminates_without_orphans(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_stub(monkeypatch, "claude_slow", tmp_path)
    runtime = ClaudeAIRuntime(timeout_seconds=1)
    with pytest.raises(DispatchError) as ei:
        asyncio.run(runtime.dispatch("x", {"workflow_step": "smoke"}))
    assert "timeout after 1s" in str(ei.value)
    # No orphaned stub children named claude_slow / claude on PATH
    time.sleep(0.2)
    proc = subprocess.run(
        ["pgrep", "-f", str(tmp_path / "bin" / "claude")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.stdout.strip() == ""


@pytest.mark.unit
def test_term_grace_constant_is_documented() -> None:
    assert _TERM_GRACE_SECONDS >= 1.0
