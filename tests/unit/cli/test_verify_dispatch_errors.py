"""Defensive-error coverage for `_verify_dispatch` (Story 2A.10).

The integration + e2e suites exercise the happy path. This file targets
the *error* branches that are otherwise unreachable without complex mock
setups: workflow-spec load failure, registry load failure, dispatch
failure, frontmatter-append failure, and dispatch outcome != "success".
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest import mock

import pytest
import typer
from pydantic import ValidationError

from sdlc.cli import _verify_dispatch as vd
from sdlc.errors import WorkflowError

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_ctx(json_mode: bool = True) -> typer.Context:
    """Return a Typer-style context that surfaces `emit_error` as `SystemExit`."""
    cmd = typer.Typer().registered_commands  # noqa: F841 — touched only for parity
    ctx = mock.MagicMock(spec=typer.Context)
    ctx.obj = {"json": json_mode}
    return ctx


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A pretend repo root with the .claude/state directory laid out."""
    (tmp_path / ".claude" / "state").mkdir(parents=True)
    (tmp_path / "03-Implementation").mkdir()
    (tmp_path / "01-Requirement").mkdir()
    return tmp_path


# ---------------------------------------------------------------------------
# _load_workflow_and_registry: error branches (lines 148-150, 159-160)
# ---------------------------------------------------------------------------


def test_load_workflow_raises_emits_infrastructure_error(repo: Path) -> None:
    """`WorkflowRegistry.load` raising `WorkflowError` becomes `ERR_INFRASTRUCTURE`."""
    ctx = _make_ctx()

    fake_registry_cls = mock.MagicMock()
    fake_registry_cls.load.side_effect = WorkflowError(
        "synthetic load fail", details={"path": "/x/y"}
    )

    with (
        mock.patch.object(vd, "_workflows_package_dir", return_value=Path("/tmp/nowhere")),
        mock.patch("sdlc.workflows.registry.WorkflowRegistry", fake_registry_cls),
        mock.patch.object(vd, "emit_error", side_effect=SystemExit(1)) as emit,
    ):
        with pytest.raises(SystemExit):
            vd._load_workflow_and_registry(ctx, repo)
        args, _kwargs = emit.call_args
        assert args[0] == "ERR_INFRASTRUCTURE"
        assert "workflow load failed" in args[1]


def test_load_registry_raises_emits_infrastructure_error(repo: Path) -> None:
    """`load_registry` raising any Exception becomes `ERR_INFRASTRUCTURE`."""
    ctx = _make_ctx()

    fake_spec = mock.MagicMock()
    fake_wf_registry_cls = mock.MagicMock()
    fake_wf_registry_cls.load.return_value.get.return_value = fake_spec

    with (
        mock.patch.object(vd, "_workflows_package_dir", return_value=Path("/tmp/nowhere")),
        mock.patch("sdlc.workflows.registry.WorkflowRegistry", fake_wf_registry_cls),
        mock.patch("sdlc.specialists.load_registry", side_effect=RuntimeError("agents missing")),
        mock.patch.object(vd, "emit_error", side_effect=SystemExit(1)) as emit,
    ):
        with pytest.raises(SystemExit):
            vd._load_workflow_and_registry(ctx, repo)
        args, _kwargs = emit.call_args
        assert args[0] == "ERR_INFRASTRUCTURE"
        assert "specialist registry load failed" in args[1]


# ---------------------------------------------------------------------------
# _run_dispatch_under_mock: error branches (203-214)
# ---------------------------------------------------------------------------


def test_run_dispatch_workflow_error_emits_user_input_error(repo: Path) -> None:
    """A `WorkflowError` inside dispatch is mapped to `ERR_USER_INPUT`."""
    ctx = _make_ctx()
    artifact_path = repo / "01-Requirement" / "x.md"
    artifact_path.write_text("body", encoding="utf-8")

    with (
        mock.patch.object(
            vd, "_materialize_verifier_fixture", side_effect=WorkflowError("specialist missing")
        ),
        mock.patch.object(vd, "emit_error", side_effect=SystemExit(1)) as emit,
    ):
        with pytest.raises(SystemExit):
            vd._run_dispatch_under_mock(
                ctx,
                spec=mock.MagicMock(),
                registry=mock.MagicMock(),
                root=repo,
                journal_path=repo / "journal.log",
                agent_runs_path=repo / "runs.jsonl",
                observer=mock.MagicMock(),
                artifact_path=artifact_path,
                artifact_content="body",
            )
        args, _kwargs = emit.call_args
        assert args[0] == "ERR_USER_INPUT"


def test_run_dispatch_generic_exception_emits_panel_dispatch_failed(repo: Path) -> None:
    """A generic `Exception` inside dispatch is mapped to `ERR_PANEL_DISPATCH_FAILED`."""
    ctx = _make_ctx()
    artifact_path = repo / "01-Requirement" / "x.md"
    artifact_path.write_text("body", encoding="utf-8")

    with (
        mock.patch.object(
            vd, "_materialize_verifier_fixture", side_effect=RuntimeError("synthetic")
        ),
        mock.patch.object(vd, "emit_error", side_effect=SystemExit(1)) as emit,
    ):
        with pytest.raises(SystemExit):
            vd._run_dispatch_under_mock(
                ctx,
                spec=mock.MagicMock(),
                registry=mock.MagicMock(),
                root=repo,
                journal_path=repo / "journal.log",
                agent_runs_path=repo / "runs.jsonl",
                observer=mock.MagicMock(),
                artifact_path=artifact_path,
                artifact_content="body",
            )
        args, _kwargs = emit.call_args
        assert args[0] == "ERR_PANEL_DISPATCH_FAILED"


def test_run_dispatch_keyboard_interrupt_propagates(repo: Path) -> None:
    """`KeyboardInterrupt` MUST bubble up, never swallowed as dispatch failure."""
    ctx = _make_ctx()
    artifact_path = repo / "01-Requirement" / "x.md"
    artifact_path.write_text("body", encoding="utf-8")

    with (
        mock.patch.object(vd, "_materialize_verifier_fixture", side_effect=KeyboardInterrupt()),
        pytest.raises(KeyboardInterrupt),
    ):
        vd._run_dispatch_under_mock(
            ctx,
            spec=mock.MagicMock(),
            registry=mock.MagicMock(),
            root=repo,
            journal_path=repo / "journal.log",
            agent_runs_path=repo / "runs.jsonl",
            observer=mock.MagicMock(),
            artifact_path=artifact_path,
            artifact_content="body",
        )


# ---------------------------------------------------------------------------
# invoke_dispatch: outcome != "success" (line 277) +
# validation-error (295-296) + frontmatter-append failure (305-307)
# ---------------------------------------------------------------------------


def _bypass_load(ctx: Any, root: Path) -> tuple[object, object]:
    spec = mock.MagicMock()
    spec.primary_agent = "artifact-verifier"
    return spec, mock.MagicMock()


def test_invoke_dispatch_outcome_failure_emits_panel_dispatch_failed(repo: Path) -> None:
    """If the dispatcher returns ``outcome != "success"``, raise ERR_PANEL_DISPATCH_FAILED."""
    ctx = _make_ctx(json_mode=True)
    artifact_path = repo / "01-Requirement" / "doc.md"
    artifact_path.write_text("body", encoding="utf-8")

    fake_result = mock.MagicMock()
    fake_result.outcome = "hook_rejected"

    with (
        mock.patch.object(vd, "_load_workflow_and_registry", side_effect=_bypass_load),
        mock.patch.object(vd, "_run_dispatch_under_mock", return_value=fake_result),
        mock.patch.object(vd, "emit_error", side_effect=SystemExit(1)) as emit,
    ):
        with pytest.raises(SystemExit):
            vd.invoke_dispatch(
                ctx=ctx,
                root=repo,
                artifact_path=artifact_path,
                artifact_id="01-Requirement/doc.md",
                artifact_content="body",
            )
        args, kwargs = emit.call_args
        assert args[0] == "ERR_PANEL_DISPATCH_FAILED"
        assert "hook_rejected" in kwargs["details"]["outcome"]


def test_invoke_dispatch_build_entry_validation_error_handled(repo: Path) -> None:
    """A `ValidationError` from `build_verification_entry` becomes ERR_INFRASTRUCTURE."""
    ctx = _make_ctx(json_mode=True)
    artifact_path = repo / "01-Requirement" / "doc.md"
    artifact_path.write_text("body", encoding="utf-8")

    fake_agent_result = mock.MagicMock()
    fake_agent_result.output_text = '{"verdict": "verified", "note": "ok"}'
    fake_result = mock.MagicMock()
    fake_result.outcome = "success"
    fake_result.agent_result = fake_agent_result

    # Force build_verification_entry to raise ValidationError
    try:
        from sdlc.cli._verify_frontmatter import _Verification

        _Verification(verifier="x", ts="bad-ts", content_hash_at_verify="bad-hash")
    except ValidationError as real_validation_error:
        forced = real_validation_error
    else:  # pragma: no cover — sanity guard
        raise AssertionError("ValidationError fixture failed to construct")

    with (
        mock.patch.object(vd, "_load_workflow_and_registry", side_effect=_bypass_load),
        mock.patch.object(vd, "_run_dispatch_under_mock", return_value=fake_result),
        mock.patch.object(vd, "build_verification_entry", side_effect=forced),
        mock.patch.object(vd, "emit_error", side_effect=SystemExit(1)) as emit,
    ):
        with pytest.raises(SystemExit):
            vd.invoke_dispatch(
                ctx=ctx,
                root=repo,
                artifact_path=artifact_path,
                artifact_id="01-Requirement/doc.md",
                artifact_content="body",
            )
        args, _kwargs = emit.call_args
        assert args[0] == "ERR_INFRASTRUCTURE"
        assert "verification entry construction failed" in args[1]


def test_invoke_dispatch_frontmatter_append_workflow_error_handled(repo: Path) -> None:
    """A `WorkflowError` from `append_and_persist_frontmatter` becomes ERR_INFRASTRUCTURE."""
    ctx = _make_ctx(json_mode=True)
    artifact_path = repo / "01-Requirement" / "doc.md"
    artifact_path.write_text("body", encoding="utf-8")

    fake_agent_result = mock.MagicMock()
    fake_agent_result.output_text = '{"verdict": "verified", "note": "ok"}'
    fake_result = mock.MagicMock()
    fake_result.outcome = "success"
    fake_result.agent_result = fake_agent_result

    fake_entry = mock.MagicMock()

    with (
        mock.patch.object(vd, "_load_workflow_and_registry", side_effect=_bypass_load),
        mock.patch.object(vd, "_run_dispatch_under_mock", return_value=fake_result),
        mock.patch.object(vd, "build_verification_entry", return_value=fake_entry),
        mock.patch.object(
            vd,
            "append_and_persist_frontmatter",
            side_effect=WorkflowError("rejected list", details={"why": "shape"}),
        ),
        mock.patch.object(vd, "emit_error", side_effect=SystemExit(1)) as emit,
    ):
        with pytest.raises(SystemExit):
            vd.invoke_dispatch(
                ctx=ctx,
                root=repo,
                artifact_path=artifact_path,
                artifact_id="01-Requirement/doc.md",
                artifact_content="body",
            )
        args, kwargs = emit.call_args
        assert args[0] == "ERR_INFRASTRUCTURE"
        assert "frontmatter append failed" in args[1]
        assert kwargs["details"]["why"] == "shape"
