"""Targeted coverage tests for branches added by the 2A.1 review patches.

Each test exercises a specific uncovered line/branch introduced or modified by
the review-driven rewrite of ``loader.py`` / ``registry.py`` / ``static_check.py``.
Tests assert behavior, not just coverage — names describe the invariant under
test rather than the line number.
"""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType

import pytest
import yaml

from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.errors import WorkflowError
from sdlc.workflows import load_workflow
from sdlc.workflows.loader import (
    _coerce_iterable_to_tuple,
    _iter_one_field,
    _safe_repr,
)
from sdlc.workflows.registry import WorkflowRegistry, _normalize_slash_command
from sdlc.workflows.static_check import (
    _resolve_known_agents,
    _segment_witness,
    _witness_both_doublestar,
    validate_workflow,
)


def _make_spec_with_globs(
    write_globs: dict[str, list[str]],
    *,
    primary: str = "agent-a",
    parallel: list[str] | None = None,
    synthesizer: str | None = None,
) -> WorkflowSpec:
    return WorkflowSpec.model_validate(
        {
            "schema_version": 1,
            "name": "cov-test",
            "slash_command": "/cov-test",
            "primary_agent": primary,
            "parallel_agents": parallel or [],
            "synthesizer_agent": synthesizer,
            "write_globs": write_globs,
            "stop_on_postcondition_failure": True,
        }
    )


@pytest.mark.unit
class TestLoaderSanitizers:
    def test_safe_repr_escapes_control_characters_for_log_safety(self) -> None:
        # P28: malicious YAML key with ANSI escape must be escaped before
        # being embedded in error messages.
        ansi_clear = "\x1b[2J\x1b[H"
        out = _safe_repr(ansi_clear)
        # ANSI escape (0x1b) renders as \x1b in unicode_escape form.
        assert "\\x1b" in out
        # No raw escape character present in output.
        assert "\x1b" not in out

    def test_coerce_iterable_to_tuple_handles_set(self) -> None:
        # P27: YAML !!set tag produces a Python set; loader must coerce
        # deterministically (sorted) so pydantic's strict validator accepts it.
        data: dict[object, object] = {"parallel_agents": {"b-agent", "a-agent"}}
        _coerce_iterable_to_tuple(data, "parallel_agents")
        assert data["parallel_agents"] == ("a-agent", "b-agent")

    def test_coerce_iterable_to_tuple_handles_frozenset(self) -> None:
        data: dict[object, object] = {"postconditions": frozenset({"y", "x"})}
        _coerce_iterable_to_tuple(data, "postconditions")
        assert data["postconditions"] == ("x", "y")

    def test_coerce_iterable_to_tuple_no_op_for_missing_key(self) -> None:
        data: dict[object, object] = {}
        _coerce_iterable_to_tuple(data, "absent")
        assert data == {}

    def test_required_string_field_empty_raises(self, tmp_path: Path) -> None:
        # P23: empty string for required field is rejected at load time.
        path = tmp_path / "empty_name.yaml"
        path.write_text(
            "schema_version: 1\nname: ''\nslash_command: /foo\nprimary_agent: a\nwrite_globs: {}\n",
            encoding="utf-8",
        )
        with pytest.raises(WorkflowError) as exc_info:
            load_workflow(path)
        assert "is empty" in str(exc_info.value)
        assert exc_info.value.details["field"] == "name"

    def test_required_string_field_whitespace_only_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "whitespace_primary.yaml"
        path.write_text(
            "schema_version: 1\nname: ok\nslash_command: /foo\n"
            "primary_agent: '   '\nwrite_globs: {}\n",
            encoding="utf-8",
        )
        with pytest.raises(WorkflowError) as exc_info:
            load_workflow(path)
        assert exc_info.value.details["field"] == "primary_agent"


@pytest.mark.unit
class TestIterStringFields:
    def test_iter_one_field_returns_tuple_items(self) -> None:
        spec = _make_spec_with_globs({}, parallel=["alpha", "beta"])
        items = list(_iter_one_field(spec, "parallel_agents"))
        assert items == [("parallel_agents[0]", "alpha"), ("parallel_agents[1]", "beta")]

    def test_iter_one_field_skips_none_optional(self) -> None:
        spec = _make_spec_with_globs({}, synthesizer=None)
        assert list(_iter_one_field(spec, "synthesizer_agent")) == []


@pytest.mark.unit
class TestRegistryGuards:
    def test_post_init_rejects_non_proxy_mapping(self) -> None:
        # Direct construction with a plain dict bypasses the safety contract.
        with pytest.raises(WorkflowError) as exc_info:
            WorkflowRegistry(_workflows={})  # type: ignore[arg-type]
        assert "must be a MappingProxyType" in str(exc_info.value)

    def test_get_unknown_slash_command_raises(self, tmp_path: Path) -> None:
        registry = WorkflowRegistry.load(tmp_path)  # empty dir → empty registry
        with pytest.raises(WorkflowError) as exc_info:
            registry.get("/never-registered")
        assert "unknown slash_command" in str(exc_info.value)
        assert exc_info.value.details["slash_command"] == "/never-registered"

    def test_normalize_slash_command_collapses_case_and_whitespace(self) -> None:
        # P14: case + whitespace folding ensures /Foo and / foo collide.
        assert _normalize_slash_command("/Foo") == _normalize_slash_command(" /foo ")

    def test_collect_workflow_paths_skips_dotfile_yaml(self, tmp_path: Path) -> None:
        # P13: hidden ``.injected.yaml`` must NOT be loaded.
        valid = tmp_path / "valid.yaml"
        valid.write_text(
            "schema_version: 1\nname: ok\nslash_command: /ok\nprimary_agent: a\nwrite_globs: {}\n",
            encoding="utf-8",
        )
        injected = tmp_path / ".injected.yaml"
        injected.write_text(
            "schema_version: 1\nname: bad\nslash_command: /bad\n"
            "primary_agent: a\nwrite_globs: {}\n",
            encoding="utf-8",
        )
        registry = WorkflowRegistry.load(tmp_path)
        # Only the visible workflow is registered.
        commands = [w.slash_command for w in registry.list()]
        assert commands == ["/ok"]

    def test_collect_workflow_paths_finds_yml_extension(self, tmp_path: Path) -> None:
        # P13: ``.yml`` should also register.
        path = tmp_path / "yml_variant.yml"
        path.write_text(
            "schema_version: 1\nname: ok\nslash_command: /yml\nprimary_agent: a\nwrite_globs: {}\n",
            encoding="utf-8",
        )
        registry = WorkflowRegistry.load(tmp_path)
        assert [w.slash_command for w in registry.list()] == ["/yml"]


@pytest.mark.unit
class TestStaticCheckBranches:
    def test_segment_witness_returns_none_for_disjoint_literals(self) -> None:
        assert _segment_witness("foo.json", "bar.md") is None

    def test_segment_witness_returns_none_when_no_wildcard_candidate_matches(self) -> None:
        # Two non-overlapping wildcard patterns: '*.json' vs 'a*.md'.
        assert _segment_witness("*.json", "a*.md") is None

    def test_witness_both_doublestar_returns_none_for_unmatchable_tails(self) -> None:
        # ('**', '**') vs ('**', 'no_match.json') with t1=() — needs t2 reachable;
        # craft an unsatisfiable shape: two ** prefixes with disjoint tails.
        result = _witness_both_doublestar(("**", "a.json"), ("**", "b.json"))
        # Tails ('a.json',) vs ('b.json',) cannot agree on one segment → None.
        assert result is None

    def test_phantom_agent_check_fires_before_disjoint_writes(self) -> None:
        spec = _make_spec_with_globs({"agent-a": ["x"], "ghost": ["y"]})
        with pytest.raises(WorkflowError) as exc_info:
            validate_workflow(spec)
        assert "phantom-agent" in str(exc_info.value)
        assert exc_info.value.details["agent"] == "ghost"

    def test_intra_agent_overlap_check_fires(self) -> None:
        spec = _make_spec_with_globs(
            {"agent-a": ["data/*.json", "data/file.json"]},
            primary="agent-a",
        )
        with pytest.raises(WorkflowError) as exc_info:
            validate_workflow(spec)
        assert "intra-agent" in str(exc_info.value)
        assert exc_info.value.details["agent"] == "agent-a"

    def test_synthesizer_agent_is_recognized_as_known(self) -> None:
        # AC8 + P5: synthesizer_agent is in the known-agents set so its
        # write_globs entry passes the phantom check.
        spec = _make_spec_with_globs(
            {"agent-a": ["a/*.json"], "synth": ["b/*.md"]},
            primary="agent-a",
            synthesizer="synth",
        )
        validate_workflow(spec)  # must not raise
        known = _resolve_known_agents(spec)
        assert "synth" in known


@pytest.mark.unit
class TestExternalDuplicateRegistration:
    def test_duplicate_slash_command_with_case_difference_raises(self, tmp_path: Path) -> None:
        # P14: case-folded duplicate detection.
        for name, slash in (("a.yaml", "/Foo"), ("b.yaml", "/foo")):
            (tmp_path / name).write_text(
                yaml.safe_dump(
                    {
                        "schema_version": 1,
                        "name": "x",
                        "slash_command": slash,
                        "primary_agent": "a",
                        "write_globs": {},
                    }
                ),
                encoding="utf-8",
            )
        with pytest.raises(WorkflowError) as exc_info:
            WorkflowRegistry.load(tmp_path)
        assert "duplicate slash_command" in str(exc_info.value)


@pytest.mark.unit
def test_workflow_registry_default_factory_is_immutable() -> None:
    # Sanity check that the default empty registry uses MappingProxyType.
    registry = WorkflowRegistry()
    assert isinstance(registry._workflows, MappingProxyType)
    assert registry.list() == ()


@pytest.mark.unit
class TestLoaderOsErrorBranches:
    """Cover differentiated OSError handling (P17/P18) without relying on
    platform-specific permission semantics."""

    def test_permission_error_raises_eacces_workflow_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "perm.yaml"
        path.write_text("schema_version: 1\n", encoding="utf-8")

        def raise_permission(self: Path, encoding: str = "utf-8") -> str:
            raise PermissionError("simulated EACCES")

        monkeypatch.setattr(Path, "read_text", raise_permission)
        with pytest.raises(WorkflowError) as exc_info:
            load_workflow(path)
        assert exc_info.value.details["errno"] == "EACCES"
        assert "permission denied" in str(exc_info.value)

    def test_generic_oserror_raises_workflow_error_with_errno(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "weird.yaml"
        path.write_text("schema_version: 1\n", encoding="utf-8")

        def raise_oserror(self: Path, encoding: str = "utf-8") -> str:
            err = OSError("simulated generic OSError")
            err.errno = 99
            raise err

        monkeypatch.setattr(Path, "read_text", raise_oserror)
        with pytest.raises(WorkflowError) as exc_info:
            load_workflow(path)
        assert exc_info.value.details["error_type"] == "OSError"
        assert "cannot read workflow file" in str(exc_info.value)

    def test_post_init_error_message_records_actual_type(self) -> None:
        # Drives the non-MappingProxy branch in __post_init__.
        with pytest.raises(WorkflowError) as exc_info:
            WorkflowRegistry(_workflows={"x": "y"})  # type: ignore[arg-type,dict-item]
        assert exc_info.value.details["actual_type"] == "dict"


@pytest.mark.unit
class TestCollectWorkflowPaths:
    def test_directory_named_like_yaml_is_skipped(self, tmp_path: Path) -> None:
        # A subdirectory matching ``*.yaml`` MUST NOT be treated as a workflow.
        (tmp_path / "looks_like.yaml").mkdir()
        (tmp_path / "real.yaml").write_text(
            "schema_version: 1\nname: ok\nslash_command: /ok\nprimary_agent: a\nwrite_globs: {}\n",
            encoding="utf-8",
        )
        registry = WorkflowRegistry.load(tmp_path)
        assert [w.slash_command for w in registry.list()] == ["/ok"]


@pytest.mark.unit
def test_iter_one_field_returns_for_non_str_non_tuple_value() -> None:
    # ``stop_on_postcondition_failure`` is bool — ``_iter_one_field`` must
    # silently skip it (no yield, no error). Drives the missing fall-through.
    spec = _make_spec_with_globs({})
    assert list(_iter_one_field(spec, "stop_on_postcondition_failure")) == []


@pytest.mark.unit
def test_iter_one_field_empty_tuple_iterates_without_yields() -> None:
    # Empty parallel_agents tuple: enters the tuple branch but never yields.
    # Forces the loop-exit edge of ``_iter_one_field``.
    spec = _make_spec_with_globs({}, parallel=[])
    assert list(_iter_one_field(spec, "parallel_agents")) == []


@pytest.mark.unit
def test_iter_one_field_skips_non_string_items_in_tuple() -> None:
    # The defensive ``if isinstance(item, str)`` guard in ``_iter_one_field``
    # protects against contract drift. WorkflowSpec's strict-mode validator
    # would normally prevent non-string entries from reaching this code, so we
    # construct a stand-in object that quacks like a frozen WorkflowSpec but
    # exposes a heterogeneous tuple under one field name.
    class _SpecLike:
        parallel_agents = ("ok-agent", 42, "another-ok")  # type: ignore[var-annotated]

    items = list(_iter_one_field(_SpecLike(), "parallel_agents"))  # type: ignore[arg-type]
    # The integer 42 must be silently skipped; the two str entries pass through.
    assert items == [
        ("parallel_agents[0]", "ok-agent"),
        ("parallel_agents[2]", "another-ok"),
    ]


@pytest.mark.unit
def test_intra_agent_overlap_iterates_past_disjoint_pair_to_find_overlap() -> None:
    # Multiple globs in one agent, only the LATER pair overlaps. Ensures the
    # ``False`` branch of the overlap check inside the combinations loop is
    # traversed before the ``True`` branch fires.
    spec = _make_spec_with_globs(
        {"agent-a": ["x/*.json", "y/*.json", "y/file.json"]},
        primary="agent-a",
    )
    with pytest.raises(WorkflowError) as exc_info:
        validate_workflow(spec)
    assert exc_info.value.details["agent"] == "agent-a"


@pytest.mark.unit
def test_extract_unknown_key_skips_extra_forbidden_with_empty_loc() -> None:
    # Drives the falsy-loc branch inside ``_extract_unknown_key``.
    from pydantic import BaseModel, ConfigDict, ValidationError

    from sdlc.workflows.loader import _extract_unknown_key

    class _Tiny(BaseModel):
        model_config = ConfigDict(extra="forbid", strict=True)
        x: int

    with pytest.raises(ValidationError) as exc_info:
        _Tiny.model_validate({"x": 1, "extra": True})
    # Real ValidationError has ('extra',) as loc, so result is "extra".
    assert _extract_unknown_key(exc_info.value) == "extra"

    # Now manually construct a ValidationError-like list without loc
    # (synthetic — covers the `if loc:` False branch).
    class _FakeExc:
        @staticmethod
        def errors() -> list[dict[str, object]]:
            return [{"type": "extra_forbidden", "loc": ()}]

    assert _extract_unknown_key(_FakeExc()) is None  # type: ignore[arg-type]
