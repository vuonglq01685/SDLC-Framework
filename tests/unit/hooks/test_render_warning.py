"""Task 4.1 — unit tests for render_warning (TDD-first, golden-style assertions)."""

from __future__ import annotations

import pytest

from sdlc.hooks.tampering import HookDrift, TamperReport, render_warning

_VALID_HASH_A = "sha256:" + "a" * 64
_VALID_HASH_B = "sha256:" + "b" * 64


def _report(
    status: str,
    drift: tuple[HookDrift, ...] = (),
    message: str = "",
    expected: dict[str, str] | None = None,
    actual: dict[str, str] | None = None,
) -> TamperReport:
    from typing import Literal, cast

    return TamperReport(
        status=cast(Literal["clean", "tampered", "uninitialized", "corrupted"], status),
        expected=expected or {},
        actual=actual or {},
        drift=drift,
        message=message,
    )


@pytest.mark.unit
class TestRenderWarningUninitialized:
    def test_uninitialized_message(self) -> None:
        report = _report("uninitialized", message="hook hashes unavailable")
        result = render_warning(report)
        assert "[WARN]" in result
        assert "hook hashes unavailable" in result
        assert "sdlc trust-hooks" in result

    def test_uninitialized_no_drift_details(self) -> None:
        report = _report("uninitialized")
        result = render_warning(report)
        assert "modified:" not in result
        assert "added:" not in result
        assert "removed:" not in result


@pytest.mark.unit
class TestRenderWarningCorrupted:
    def test_corrupted_message_contains_warn(self) -> None:
        report = _report(
            "corrupted",
            message="hook hash store at /x is corrupted: bad json; run ...",
        )
        result = render_warning(report)
        assert "[WARN]" in result

    def test_corrupted_message_contains_trust_hooks(self) -> None:
        report = _report("corrupted", message="x is corrupted: reason; run ...")
        result = render_warning(report)
        assert "trust-hooks" in result


@pytest.mark.unit
class TestRenderWarningTampered:
    def test_tampered_n1_modified_shape(self) -> None:
        drift = (
            HookDrift(
                relpath="pre_tool.py",
                expected=_VALID_HASH_A,
                actual=_VALID_HASH_B,
                kind="modified",
            ),
        )
        report = _report(
            "tampered",
            drift=drift,
            message="hook tampering detected: 1 file(s) changed since trust.",
        )
        result = render_warning(report)
        assert "[WARN] hook tampering detected: 1 file(s)" in result
        assert "modified:" in result
        assert "pre_tool.py" in result
        assert "expected:" in result
        assert "actual:" in result
        assert "sdlc trust-hooks" in result

    def test_tampered_n3_all_kinds(self) -> None:
        drift = (
            HookDrift(relpath="aa.py", expected=None, actual=_VALID_HASH_A, kind="added"),
            HookDrift(
                relpath="bb.py", expected=_VALID_HASH_A, actual=_VALID_HASH_B, kind="modified"
            ),
            HookDrift(relpath="cc.py", expected=_VALID_HASH_B, actual=None, kind="removed"),
        )
        report = _report(
            "tampered",
            drift=drift,
            message="hook tampering detected: 3 file(s) changed since trust.",
        )
        result = render_warning(report)
        assert "3 file(s)" in result
        assert "added:" in result
        assert "modified:" in result
        assert "removed:" in result
        assert "aa.py" in result
        assert "bb.py" in result
        assert "cc.py" in result

    def test_tampered_stdout_is_pure_string(self) -> None:
        drift = (
            HookDrift(
                relpath="x.py", expected=_VALID_HASH_A, actual=_VALID_HASH_B, kind="modified"
            ),
        )
        report = _report("tampered", drift=drift, message="tampered: 1 file(s)")
        result = render_warning(report)
        assert isinstance(result, str)

    def test_added_uses_correct_prefix(self) -> None:
        drift = (HookDrift(relpath="new.py", expected=None, actual=_VALID_HASH_A, kind="added"),)
        report = _report("tampered", drift=drift, message="tampered: 1 file(s)")
        result = render_warning(report)
        assert ".claude/hooks/new.py" in result

    def test_removed_uses_correct_prefix(self) -> None:
        drift = (HookDrift(relpath="gone.py", expected=_VALID_HASH_A, actual=None, kind="removed"),)
        report = _report("tampered", drift=drift, message="tampered: 1 file(s)")
        result = render_warning(report)
        assert ".claude/hooks/gone.py" in result


@pytest.mark.unit
class TestRenderWarningClean:
    def test_clean_returns_empty_string(self) -> None:
        report = _report("clean", message="hashes match.")
        result = render_warning(report)
        assert result == ""
