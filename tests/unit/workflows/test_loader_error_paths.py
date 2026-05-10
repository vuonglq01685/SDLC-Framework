"""Error-path tests for load_workflow (Story 2A.1).

P19 rewrite: drops `MagicMock`-based fakes for `ValidationError` in favor of
real ValidationError instances raised by tiny throwaway models. P21: the
unreachable `_construct_unique_mapping` non-mapping branch is now an
``assert`` (not an exception), and the corresponding test asserts AssertionError
rather than ConstructorError.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from sdlc.errors import WorkflowError
from sdlc.workflows import load_workflow
from sdlc.workflows.loader import _extract_unknown_key


class _TinyStrict(BaseModel):
    """Throwaway pydantic model used to produce real ValidationError instances."""

    model_config = ConfigDict(extra="forbid", strict=True)
    name: str
    age: int


@pytest.mark.unit
class TestLoaderErrorPaths:
    def test_missing_file_raises_file_not_found_workflow_error(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent.yaml"
        with pytest.raises(WorkflowError) as exc_info:
            load_workflow(missing)
        assert "does not exist" in str(exc_info.value)
        assert exc_info.value.details["errno"] == "ENOENT"
        assert str(missing) in str(exc_info.value)

    def test_directory_path_raises_is_a_directory_workflow_error(self, tmp_path: Path) -> None:
        with pytest.raises(WorkflowError) as exc_info:
            load_workflow(tmp_path)
        assert "is a directory" in str(exc_info.value)
        assert exc_info.value.details["errno"] == "EISDIR"

    def test_non_utf8_bytes_raise_workflow_error(self, tmp_path: Path) -> None:
        bad = tmp_path / "non_utf8.yaml"
        bad.write_bytes(b"name: \xff\xfe garbage\n")
        with pytest.raises(WorkflowError) as exc_info:
            load_workflow(bad)
        assert "not valid UTF-8" in str(exc_info.value)
        assert exc_info.value.details["error_type"] == "UnicodeDecodeError"

    def test_yaml_parse_error_raises_workflow_error(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text(":::bad yaml:::\n  - [unclosed", encoding="utf-8")
        with pytest.raises(WorkflowError) as exc_info:
            load_workflow(bad)
        assert "YAML parse error" in str(exc_info.value)

    def test_duplicate_key_raises_workflow_error(self, tmp_path: Path) -> None:
        dup = tmp_path / "dup.yaml"
        dup.write_text(
            "schema_version: 1\nname: test\nname: duplicate\nslash_command: /t\n"
            "primary_agent: a\nwrite_globs: {}\n",
            encoding="utf-8",
        )
        with pytest.raises(WorkflowError) as exc_info:
            load_workflow(dup)
        assert "YAML parse error" in str(exc_info.value)

    def test_empty_file_raises_friendly_workflow_error(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.yaml"
        empty.write_text("", encoding="utf-8")
        with pytest.raises(WorkflowError) as exc_info:
            load_workflow(empty)
        assert "empty or contains only comments" in str(exc_info.value)
        assert exc_info.value.details["reason"] == "empty_or_comments_only"

    def test_comments_only_file_raises_friendly_workflow_error(self, tmp_path: Path) -> None:
        comments = tmp_path / "comments_only.yaml"
        comments.write_text("# only a comment\n# and another\n", encoding="utf-8")
        with pytest.raises(WorkflowError) as exc_info:
            load_workflow(comments)
        assert "empty or contains only comments" in str(exc_info.value)

    def test_non_dict_yaml_raises_workflow_error(self, tmp_path: Path) -> None:
        scalar = tmp_path / "scalar.yaml"
        scalar.write_text("just a string\n", encoding="utf-8")
        with pytest.raises(WorkflowError) as exc_info:
            load_workflow(scalar)
        assert "must be a YAML mapping" in str(exc_info.value)
        assert exc_info.value.details["actual_type"] == "str"

    def test_list_yaml_raises_workflow_error(self, tmp_path: Path) -> None:
        lst = tmp_path / "list.yaml"
        lst.write_text("- item1\n- item2\n", encoding="utf-8")
        with pytest.raises(WorkflowError) as exc_info:
            load_workflow(lst)
        assert "must be a YAML mapping" in str(exc_info.value)
        assert exc_info.value.details["actual_type"] == "list"

    def test_extract_unknown_key_finds_real_extra_forbidden(self) -> None:
        """Drives ``_extract_unknown_key`` with a real ValidationError (P19)."""
        with pytest.raises(ValidationError) as exc_info:
            _TinyStrict.model_validate({"name": "x", "age": 1, "metadata": {}})
        result = _extract_unknown_key(exc_info.value)
        assert result == "metadata"

    def test_extract_unknown_key_returns_none_for_missing_field_error(self) -> None:
        """Real ValidationError with no extra_forbidden returns None (P19)."""
        with pytest.raises(ValidationError) as exc_info:
            _TinyStrict.model_validate({"name": "x"})  # missing 'age'
        result = _extract_unknown_key(exc_info.value)
        assert result is None

    def test_schema_validation_failure_does_not_leak_input_in_message(self, tmp_path: Path) -> None:
        """P8: schema-validation branch must NOT embed str(exc) (which contains
        the offending input). The error message stays generic; details report
        structured field-error metadata only."""
        bad = tmp_path / "missing_field.yaml"
        bad.write_text(
            "schema_version: 1\nname: test\nslash_command: /t\nwrite_globs: {}\n",
            encoding="utf-8",
        )
        with pytest.raises(WorkflowError) as exc_info:
            load_workflow(bad)
        msg = str(exc_info.value)
        assert "schema validation failed" in msg
        # Must NOT embed pydantic's verbose message dump.
        assert "input_value" not in msg
        # Structured details available for diagnostic consumers.
        details = exc_info.value.details
        assert details["error_type"] == "ValidationError"
        error_count = details["error_count"]
        assert isinstance(error_count, int) and error_count >= 1
        assert isinstance(details["field_errors"], list)

    def test_construct_unique_mapping_unreachable_branch_now_asserts(self) -> None:
        """P21: the previously-test-only defensive branch is now an ``assert`` so
        coverage no longer demands a fake test. Sanity: invoking the helper
        with a non-mapping node directly still surfaces a clear AssertionError."""
        import yaml

        from sdlc.workflows.loader import (
            _construct_unique_mapping,
            _NoDuplicateKeysLoader,
        )

        loader = _NoDuplicateKeysLoader("")
        seq_node = yaml.SequenceNode(tag="tag:yaml.org,2002:seq", value=[])
        with pytest.raises(AssertionError):
            _construct_unique_mapping(loader, seq_node)  # type: ignore[arg-type]
