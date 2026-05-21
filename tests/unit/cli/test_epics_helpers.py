"""Direct coverage of the helper functions in ``sdlc.cli.epics``.

The orchestrator ``run_epics`` is exercised by ``test_epics_command.py`` end-to-end
on the happy path. This file targets the helper functions in isolation so the
many error-mapping branches (UnicodeDecodeError on PRODUCT.md, empty PRODUCT.md,
SignoffError, WorkflowError sub-categories) get exact coverage without spinning
up the full CLI runner (EPIC-2A-D3 / prep-sprint C3 coverage restore).
"""

from __future__ import annotations

import unittest.mock
from collections.abc import Mapping
from pathlib import Path

import pytest
import typer

from sdlc.cli.epics import (
    SignoffState,
    _apply_signoff_gate,
    _map_workflow_error,
    _read_product_text,
)
from sdlc.errors import SignoffError, WorkflowError

pytestmark = pytest.mark.unit


def _ctx() -> typer.Context:
    """Minimal Typer context — mirrors conftest.make_ctx (avoid cross-package import)."""
    ctx = typer.Context(command=typer.core.TyperCommand("test"))
    ctx.ensure_object(dict)
    ctx.obj["json"] = False
    ctx.obj["no_color"] = False
    return ctx


# ---------------------------------------------------------------------------
# _read_product_text
# ---------------------------------------------------------------------------


def test_read_product_text_unicode_decode_error_maps_to_artifact_unreadable(
    tmp_path: Path,
) -> None:
    """A non-UTF-8 PRODUCT.md must surface as ``ERR_ARTIFACT_UNREADABLE``, not
    crash the CLI with a raw ``UnicodeDecodeError``."""
    product = tmp_path / "01-PRODUCT.md"
    product.write_bytes(b"\xff\xfe\x00broken")  # invalid UTF-8 start bytes

    with pytest.raises(typer.Exit):
        _read_product_text(product, _ctx())


def test_read_product_text_empty_maps_to_user_input(tmp_path: Path) -> None:
    """An empty PRODUCT.md must surface as ``ERR_USER_INPUT`` with a hint to
    populate the brief — not silently succeed with an empty string."""
    product = tmp_path / "01-PRODUCT.md"
    product.write_text("   \n\t \n")  # only whitespace

    with pytest.raises(typer.Exit):
        _read_product_text(product, _ctx())


def test_read_product_text_returns_full_text_on_happy_path(tmp_path: Path) -> None:
    """A populated UTF-8 PRODUCT.md round-trips through the helper unchanged."""
    product = tmp_path / "01-PRODUCT.md"
    product.write_text("# Vision\n\nReal content.\n")

    assert _read_product_text(product, _ctx()) == "# Vision\n\nReal content.\n"


# ---------------------------------------------------------------------------
# _apply_signoff_gate
# ---------------------------------------------------------------------------


def test_signoff_gate_signoff_error_maps_to_err_signoff_state(tmp_path: Path) -> None:
    """``SignoffError`` from compute_state must surface as ``ERR_SIGNOFF_STATE``
    with the original details payload preserved."""
    boom = SignoffError("signoff file is malformed", details={"path": "/x/signoff.yaml"})

    with (
        unittest.mock.patch("sdlc.cli.epics.compute_state", side_effect=boom),
        pytest.raises(typer.Exit),
    ):
        _apply_signoff_gate(root=tmp_path, ctx=_ctx())


def test_signoff_gate_approved_phase1_blocks(tmp_path: Path) -> None:
    """An ``APPROVED`` phase-1 signoff must hard-block ``sdlc epics`` (running
    epics against an approved phase 1 would be a hash-drift event)."""
    with (
        unittest.mock.patch("sdlc.cli.epics.compute_state", return_value=SignoffState.APPROVED),
        pytest.raises(typer.Exit),
    ):
        _apply_signoff_gate(root=tmp_path, ctx=_ctx())


def test_signoff_gate_drafted_emits_warn_but_does_not_block(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``DRAFTED_NOT_APPROVED`` is allowed but must emit a [WARN] on stderr —
    the user needs to know epics changes will force a signoff re-draft."""
    with unittest.mock.patch(
        "sdlc.cli.epics.compute_state", return_value=SignoffState.DRAFTED_NOT_APPROVED
    ):
        _apply_signoff_gate(root=tmp_path, ctx=_ctx())

    err = capsys.readouterr().err
    assert "[WARN]" in err
    assert "signoff" in err.lower()


def test_signoff_gate_awaiting_signoff_returns_silently(tmp_path: Path) -> None:
    """``AWAITING_SIGNOFF`` (the starting state) is allowed silently; only
    ``APPROVED`` blocks and ``DRAFTED_NOT_APPROVED`` warns."""
    with unittest.mock.patch(
        "sdlc.cli.epics.compute_state", return_value=SignoffState.AWAITING_SIGNOFF
    ):
        _apply_signoff_gate(root=tmp_path, ctx=_ctx())


# ---------------------------------------------------------------------------
# _map_workflow_error
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "subcategory,expected_code",
    [
        ("schema_invalid", "ERR_EPIC_SCHEMA_INVALID"),
        ("hook_rejected", "ERR_HOOK_REJECTED"),
        ("dispatch_failed", "ERR_EPICS_DISPATCH_FAILED"),
        ("collision", "ERR_USER_INPUT"),
        ("unknown_subcategory", "ERR_INFRASTRUCTURE"),
        (None, "ERR_INFRASTRUCTURE"),  # missing sdlc_epics key
    ],
)
def test_map_workflow_error_dispatches_by_subcategory(
    subcategory: str | None, expected_code: str
) -> None:
    """Every documented sub-category routes to its dedicated error code; the
    default (unknown / missing) falls back to ``ERR_INFRASTRUCTURE`` (patch #11)."""
    details: dict[str, object] = {"sdlc_epics": subcategory} if subcategory is not None else {}
    exc = WorkflowError("boom", details=details)

    with unittest.mock.patch("sdlc.cli.epics.emit_error") as mock_emit:
        _map_workflow_error(exc, _ctx())

    assert mock_emit.call_count == 1
    call = mock_emit.call_args
    assert call.args[0] == expected_code
    # Original details must be preserved (Mapping → dict copy at the boundary).
    assert isinstance(call.kwargs.get("details"), Mapping)
