"""Story 3.8 review (F3): a stray / out-of-enum ``tdd_strategy`` emitted by task-breaker must
NOT abort the whole ``/sdlc-break`` batch.

The CLI stamps ``tdd_strategy`` deterministically from ``touches`` (D2), so ``parse_task_array``
drops any LLM-supplied value before StrictModel validation — keeping ``task-breaker.md``'s
"it is dropped before validation" promise honest (an out-of-enum value previously raised a
``ValidationError`` → ``WorkflowError("schema_invalid")`` and failed the entire break).
"""

from __future__ import annotations

import json

import pytest

from sdlc.cli._break_pipeline import parse_task_array

pytestmark = pytest.mark.unit

_SID = "EPIC-foo-S01-bar"


def _one_task(tdd_value: str) -> str:
    return json.dumps(
        [
            {
                "id": f"{_SID}-T01-strip",
                "story_id": _SID,
                "label": "strip test",
                "stage": "pending",
                "dependencies": [],
                "tdd_strategy": tdd_value,
            }
        ]
    )


def test_out_of_enum_tdd_strategy_is_dropped_not_fatal() -> None:
    out = parse_task_array(_one_task("not-a-real-strategy"), request_story_id=_SID)
    assert len(out) == 1
    # dropped before validation → default; the CLI classifier stamps the real value later.
    assert out[0].tdd_strategy == "write-tests-first"


def test_llm_supplied_valid_tdd_strategy_is_also_ignored() -> None:
    # Even a *valid* enum value from the model is ignored (CLI is the source of truth).
    out = parse_task_array(_one_task("characterization-test"), request_story_id=_SID)
    assert out[0].tdd_strategy == "write-tests-first"
