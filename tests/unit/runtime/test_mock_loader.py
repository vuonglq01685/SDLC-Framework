from __future__ import annotations

from pathlib import Path

import pydantic
import pytest

from sdlc.errors import MockMissError
from sdlc.runtime import MockAIRuntime


def _write_smoke_yaml(directory: Path) -> None:
    """Write a minimal valid fixture file into directory."""
    (directory / "smoke.yaml").write_text(
        '"sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824":\n'
        "  output_text: hello back\n"
        "  tool_calls: []\n"
        "  tokens_in: 1\n"
        "  tokens_out: 2\n",
        encoding="utf-8",
    )


@pytest.mark.unit
def test_construct_mock_with_nonexistent_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(MockMissError) as ei:
        MockAIRuntime(fixtures_dir=tmp_path / "nope")
    assert ei.value.details["step"] == "fixtures_dir_check"


@pytest.mark.unit
def test_construct_mock_with_file_not_dir_raises(tmp_path: Path) -> None:
    afile = tmp_path / "afile.txt"
    afile.touch()
    with pytest.raises(MockMissError) as ei:
        MockAIRuntime(fixtures_dir=afile)
    assert ei.value.details["step"] == "fixtures_dir_check"


@pytest.mark.unit
def test_construct_mock_with_empty_dir_succeeds(tmp_path: Path) -> None:
    fx = tmp_path / "fx"
    fx.mkdir()
    mock = MockAIRuntime(fixtures_dir=fx)
    assert mock._fixtures == {}


@pytest.mark.unit
def test_construct_mock_loads_single_yaml_fixture(tmp_path: Path) -> None:
    fx = tmp_path / "fx"
    fx.mkdir()
    _write_smoke_yaml(fx)
    mock = MockAIRuntime(fixtures_dir=fx)
    key = ("smoke", "sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824")
    assert key in mock._fixtures


@pytest.mark.unit
def test_construct_mock_with_malformed_yaml_raises(tmp_path: Path) -> None:
    fx = tmp_path / "fx"
    fx.mkdir()
    (fx / "bad.yaml").write_text("key: value: bad: :\n", encoding="utf-8")
    with pytest.raises(MockMissError) as ei:
        MockAIRuntime(fixtures_dir=fx)
    assert ei.value.details["step"] == "fixture_yaml_parse"


@pytest.mark.unit
def test_construct_mock_with_top_level_list_raises(tmp_path: Path) -> None:
    fx = tmp_path / "fx"
    fx.mkdir()
    (fx / "list.yaml").write_text("- item1\n- item2\n", encoding="utf-8")
    with pytest.raises(MockMissError) as ei:
        MockAIRuntime(fixtures_dir=fx)
    assert ei.value.details["step"] == "fixture_yaml_shape"


@pytest.mark.unit
def test_construct_mock_with_non_sha256_key_raises(tmp_path: Path) -> None:
    fx = tmp_path / "fx"
    fx.mkdir()
    (fx / "bad_key.yaml").write_text(
        "not-a-hash:\n  output_text: x\n  tokens_in: 1\n  tokens_out: 1\n",
        encoding="utf-8",
    )
    with pytest.raises(MockMissError) as ei:
        MockAIRuntime(fixtures_dir=fx)
    assert ei.value.details["step"] == "fixture_key_shape"


@pytest.mark.unit
def test_construct_mock_with_extra_field_in_record_raises(tmp_path: Path) -> None:
    fx = tmp_path / "fx"
    fx.mkdir()
    (fx / "extra.yaml").write_text(
        '"sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824":\n'
        "  output_text: x\n"
        "  tokens_in: 1\n"
        "  tokens_out: 1\n"
        "  extra_field: oops\n",
        encoding="utf-8",
    )
    with pytest.raises(pydantic.ValidationError):
        MockAIRuntime(fixtures_dir=fx)


@pytest.mark.unit
def test_construct_mock_with_negative_tokens_raises(tmp_path: Path) -> None:
    fx = tmp_path / "fx"
    fx.mkdir()
    (fx / "neg.yaml").write_text(
        '"sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824":\n'
        "  output_text: x\n"
        "  tokens_in: -1\n"
        "  tokens_out: 1\n",
        encoding="utf-8",
    )
    with pytest.raises(pydantic.ValidationError):
        MockAIRuntime(fixtures_dir=fx)


@pytest.mark.unit
def test_construct_mock_with_bool_tokens_raises(tmp_path: Path) -> None:
    """`tokens_in: true` must NOT silently coerce to 1; strict=True rejects bool."""
    fx = tmp_path / "fx"
    fx.mkdir()
    (fx / "bool.yaml").write_text(
        '"sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824":\n'
        "  output_text: x\n"
        "  tokens_in: true\n"
        "  tokens_out: 1\n",
        encoding="utf-8",
    )
    with pytest.raises(pydantic.ValidationError):
        MockAIRuntime(fixtures_dir=fx)


@pytest.mark.unit
def test_construct_mock_rejects_yml_sibling_extension(tmp_path: Path) -> None:
    """Sibling `.yml` files are rejected fail-loud so authors don't lose fixtures to a typo."""
    fx = tmp_path / "fx"
    fx.mkdir()
    _write_smoke_yaml(fx)
    (fx / "typo.yml").write_text("anything\n", encoding="utf-8")
    with pytest.raises(MockMissError) as ei:
        MockAIRuntime(fixtures_dir=fx)
    assert ei.value.details["step"] == "fixture_extension_check"
    assert ".yml" in str(ei.value)


@pytest.mark.unit
def test_construct_mock_with_empty_yaml_raises(tmp_path: Path) -> None:
    """Empty / comment-only YAML files surface as a clear error, not silent skip."""
    fx = tmp_path / "fx"
    fx.mkdir()
    (fx / "empty.yaml").write_text("# only a comment\n", encoding="utf-8")
    with pytest.raises(MockMissError) as ei:
        MockAIRuntime(fixtures_dir=fx)
    assert ei.value.details["step"] == "fixture_yaml_empty"


@pytest.mark.unit
def test_construct_mock_with_duplicate_yaml_keys_raises(tmp_path: Path) -> None:
    """Duplicate `sha256:...` keys in one YAML file fail-loud (override PyYAML last-wins)."""
    fx = tmp_path / "fx"
    fx.mkdir()
    same_key = "sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    (fx / "dup.yaml").write_text(
        f'"{same_key}":\n'
        "  output_text: first\n"
        "  tokens_in: 1\n"
        "  tokens_out: 1\n"
        f'"{same_key}":\n'
        "  output_text: second\n"
        "  tokens_in: 2\n"
        "  tokens_out: 2\n",
        encoding="utf-8",
    )
    with pytest.raises(MockMissError) as ei:
        MockAIRuntime(fixtures_dir=fx)
    assert ei.value.details["step"] == "fixture_yaml_parse"
    assert "duplicate key" in str(ei.value)
