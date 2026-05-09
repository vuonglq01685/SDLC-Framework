from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path

import pytest

from sdlc.runtime import MockAIRuntime

_SMOKE_HASH = "sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
_SMOKE_YAML = (
    f'"{_SMOKE_HASH}":\n'
    "  output_text: hello back\n"
    "  tool_calls: []\n"
    "  tokens_in: 1\n"
    "  tokens_out: 2\n"
)


def _make_mock(tmp_path: Path) -> MockAIRuntime:
    fx = tmp_path / "fx"
    fx.mkdir()
    (fx / "smoke.yaml").write_text(_SMOKE_YAML, encoding="utf-8")
    return MockAIRuntime(fixtures_dir=fx)


def _canonical_bytes(result: object) -> bytes:
    import json as _json

    from sdlc.runtime import AgentResult

    assert isinstance(result, AgentResult)
    return _json.dumps(
        result.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


@pytest.mark.unit
def test_dispatch_same_input_returns_byte_identical_result(tmp_path: Path) -> None:
    mock = _make_mock(tmp_path)
    results = [asyncio.run(mock.dispatch("hello", {"workflow_step": "smoke"})) for _ in range(10)]
    canonical = [_canonical_bytes(r) for r in results]
    assert all(c == canonical[0] for c in canonical), "non-deterministic mock!"


@pytest.mark.unit
def test_dispatch_concurrent_calls_return_byte_identical_results(tmp_path: Path) -> None:
    mock = _make_mock(tmp_path)

    async def _run() -> list[object]:
        return await asyncio.gather(
            *[mock.dispatch("hello", {"workflow_step": "smoke"}) for _ in range(20)]
        )

    results = asyncio.run(_run())
    canonical = [_canonical_bytes(r) for r in results]
    assert all(c == canonical[0] for c in canonical), "concurrent calls returned different results!"


@pytest.mark.unit
def test_dispatch_different_prompts_return_different_fixtures_when_differ(tmp_path: Path) -> None:
    import hashlib

    fx = tmp_path / "fx"
    fx.mkdir()
    hash1 = "sha256:" + hashlib.sha256(b"prompt-one").hexdigest()
    hash2 = "sha256:" + hashlib.sha256(b"prompt-two").hexdigest()
    (fx / "step.yaml").write_text(
        f'"{hash1}":\n'
        "  output_text: result one\n"
        "  tokens_in: 1\n"
        "  tokens_out: 1\n"
        f'"{hash2}":\n'
        "  output_text: result two\n"
        "  tokens_in: 2\n"
        "  tokens_out: 2\n",
        encoding="utf-8",
    )
    mock = MockAIRuntime(fixtures_dir=fx)
    r1 = asyncio.run(mock.dispatch("prompt-one", {"workflow_step": "step"}))
    r2 = asyncio.run(mock.dispatch("prompt-two", {"workflow_step": "step"}))
    assert r1.output_text == "result one"
    assert r2.output_text == "result two"


@pytest.mark.integration
def test_prompt_hash_is_stable_across_python_runs(tmp_path: Path) -> None:
    if not shutil.which("uv"):
        pytest.skip("uv not available")
    # Resolve repo root from the test file's location so the test runs on any developer
    # machine and on CI — NOT a hardcoded absolute path.
    repo_root = Path(__file__).resolve().parents[3]
    assert (repo_root / "pyproject.toml").is_file(), (
        f"expected pyproject.toml at {repo_root}; test layout assumption broken"
    )
    script = tmp_path / "hash.py"
    script.write_text(
        "from sdlc.runtime.mock import _hash_prompt; print(_hash_prompt('hello'))",
        encoding="utf-8",
    )
    out1 = subprocess.run(
        ["uv", "run", "python", str(script)],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(repo_root),
    ).stdout.strip()
    out2 = subprocess.run(
        ["uv", "run", "python", str(script)],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(repo_root),
    ).stdout.strip()
    assert out1 == out2 == _SMOKE_HASH
