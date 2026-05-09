from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import pytest

from sdlc.errors import MockMissError
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


@pytest.mark.unit
def test_dispatch_hit_returns_fixture_result(tmp_path: Path) -> None:
    mock = _make_mock(tmp_path)
    result = asyncio.run(mock.dispatch("hello", {"workflow_step": "smoke"}))
    assert result.output_text == "hello back"
    assert result.tokens_in == 1
    assert result.tokens_out == 2


@pytest.mark.unit
def test_dispatch_miss_raises_mock_miss_error(tmp_path: Path) -> None:
    mock = _make_mock(tmp_path)
    with pytest.raises(MockMissError) as ei:
        asyncio.run(mock.dispatch("not-in-fixtures", {"workflow_step": "smoke"}))
    assert ei.value.details["step"] == "fixture_lookup"
    assert "add a YAML at" in str(ei.value)


@pytest.mark.unit
def test_dispatch_miss_includes_correct_prompt_hash_in_message(tmp_path: Path) -> None:
    mock = _make_mock(tmp_path)
    prompt = "unique test prompt xyz"
    expected_hash = "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    with pytest.raises(MockMissError) as ei:
        asyncio.run(mock.dispatch(prompt, {"workflow_step": "smoke"}))
    assert expected_hash in str(ei.value)


@pytest.mark.unit
def test_dispatch_miss_when_workflow_step_missing(tmp_path: Path) -> None:
    mock = _make_mock(tmp_path)
    with pytest.raises(MockMissError) as ei:
        asyncio.run(mock.dispatch("hello", {}))
    assert ei.value.details["workflow_step"] == ""


@pytest.mark.unit
def test_dispatch_with_non_string_workflow_step_raises(tmp_path: Path) -> None:
    """workflow_step must be str; ints / None fail-loud rather than silently coerce."""
    mock = _make_mock(tmp_path)
    with pytest.raises(MockMissError) as ei:
        asyncio.run(mock.dispatch("hello", {"workflow_step": 42}))
    assert ei.value.details["step"] == "workflow_step_type"
    assert ei.value.details["workflow_step_type"] == "int"


@pytest.mark.unit
def test_dispatch_with_lone_surrogate_prompt_raises(tmp_path: Path) -> None:
    """Lone-surrogate prompts surface as MockMissError, not raw UnicodeEncodeError."""
    mock = _make_mock(tmp_path)
    with pytest.raises(MockMissError) as ei:
        # \ud800 is a high-surrogate without its low-surrogate pair; not UTF-8 encodable.
        asyncio.run(mock.dispatch("\ud800", {"workflow_step": "smoke"}))
    assert ei.value.details["step"] == "prompt_encode"


@pytest.mark.unit
def test_dispatch_yields_control_at_least_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify dispatch actually awaits asyncio.sleep(0) — not a tautology.

    A coroutine that never `await`s is observably different from one that does
    (Decision C2 / abstraction-adequacy). Removing `await asyncio.sleep(0)` from
    `mock.dispatch` would let a real-Claude race-bug class go undetected by
    Story 1.14's abstraction-adequacy CI test. This test fails fast if the yield
    is removed by monkeypatching `asyncio.sleep` and asserting it was invoked
    with delay=0 during dispatch.
    """
    mock = _make_mock(tmp_path)

    sleep_calls: list[float] = []
    real_sleep = asyncio.sleep

    async def tracking_sleep(delay: float) -> None:
        sleep_calls.append(delay)
        await real_sleep(delay)

    import sdlc.runtime.mock as mock_module

    monkeypatch.setattr(mock_module.asyncio, "sleep", tracking_sleep)

    asyncio.run(mock.dispatch("hello", {"workflow_step": "smoke"}))
    assert 0 in sleep_calls, (
        "dispatch did not call asyncio.sleep(0); abstraction-adequacy guarantee broken"
    )
