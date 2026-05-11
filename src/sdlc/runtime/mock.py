"""MockAIRuntime — deterministic YAML-driven AIRuntime for tests (Decision C2, Architecture §356).

Loads tests/fixtures/mock_responses/*.yaml at construction time;
dispatch keyed by (workflow_step, prompt_hash). Missing key raises MockMissError.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar, Final

import yaml
from pydantic import BaseModel, ConfigDict, Field

from sdlc.errors import MockMissError
from sdlc.runtime.abc import AgentResult, AIRuntime

_SHA256_PREFIX: Final[str] = "sha256:"
_FIXTURE_GLOB: Final[str] = "*.yaml"
# Sibling YAML extensions that are explicitly rejected so authors do not silently
# lose a fixture file to a typo. Lowercase ".yaml" is the only accepted form.
_REJECTED_EXTENSIONS: Final[tuple[str, ...]] = (".yml", ".YAML", ".YML")


class _Fixture(BaseModel):
    """Internal: validates YAML fixture records at load time. Not exported."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=False,
    )

    output_text: str
    tool_calls: tuple[Mapping[str, object], ...] = Field(default_factory=tuple)
    # strict=True rejects bool → int coercion (True/False are int subclasses in Python).
    tokens_in: int = Field(ge=0, strict=True)
    tokens_out: int = Field(ge=0, strict=True)

    def as_agent_result(self) -> AgentResult:
        return AgentResult(
            output_text=self.output_text,
            tool_calls=self.tool_calls,
            tokens_in=self.tokens_in,
            tokens_out=self.tokens_out,
        )


def _hash_prompt(prompt: str) -> str:
    """Compute deterministic prompt hash for MockAIRuntime keying.

    Raises:
        MockMissError: if `prompt` cannot be UTF-8 encoded (e.g., contains lone surrogates).
    """
    try:
        encoded = prompt.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise MockMissError(
            f"prompt is not encodable as UTF-8: {exc}",
            details={"step": "prompt_encode", "error": str(exc)},
        ) from exc
    return _SHA256_PREFIX + hashlib.sha256(encoded).hexdigest()


# Public alias — single canonical implementation lives in `_hash_prompt` to prevent drift.
compute_prompt_hash = _hash_prompt


class _NoDuplicateKeysLoader(yaml.SafeLoader):
    """SafeLoader subclass that raises on duplicate mapping keys.

    PyYAML's default last-wins behavior silently swallows authoring errors; this
    loader fails-loud instead. Used in `_load_fixtures` only.
    """


def _construct_unique_mapping(
    loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[object, object]:
    if not isinstance(node, yaml.MappingNode):
        raise yaml.constructor.ConstructorError(
            None,
            None,
            f"expected a mapping node, but found {node.id}",
            node.start_mark,
        )
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)  # type: ignore[no-untyped-call]
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)  # type: ignore[no-untyped-call]
    return mapping


_NoDuplicateKeysLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _check_fixtures_dir(fixtures_dir: Path) -> None:
    """Validate `fixtures_dir` exists, is a directory, and contains only `.yaml` files."""
    if not fixtures_dir.exists():
        raise MockMissError(
            f"fixtures_dir does not exist: {fixtures_dir}",
            details={"step": "fixtures_dir_check", "fixtures_dir": str(fixtures_dir)},
        )
    if not fixtures_dir.is_dir():
        raise MockMissError(
            f"fixtures_dir is not a directory: {fixtures_dir}",
            details={"step": "fixtures_dir_check", "fixtures_dir": str(fixtures_dir)},
        )
    # Reject sibling YAML extensions explicitly so a typo does not silently hide a fixture.
    for entry in fixtures_dir.iterdir():
        if entry.is_file() and entry.suffix in _REJECTED_EXTENSIONS:
            raise MockMissError(
                f"unsupported fixture extension {entry.suffix} at {entry};"
                " rename to '.yaml' (lowercase). Mixed extensions are not supported.",
                details={
                    "step": "fixture_extension_check",
                    "fixture_path": str(entry),
                },
            )


def _parse_fixture_file(yaml_path: Path, workflow_step: str) -> dict[object, object]:
    """Read+parse a single fixture file; raise MockMissError on malformed/empty/non-mapping."""
    try:
        content = yaml_path.read_text(encoding="utf-8")
        data = yaml.load(content, Loader=_NoDuplicateKeysLoader)
    except (OSError, yaml.YAMLError) as exc:
        raise MockMissError(
            f"malformed fixture file {yaml_path}: {exc}",
            details={
                "step": "fixture_yaml_parse",
                "fixture_path": str(yaml_path),
                "workflow_step": workflow_step,
            },
        ) from exc
    if data is None:
        # Empty or comment-only file — surface clearly rather than treat as empty mapping.
        raise MockMissError(
            f"empty fixture file {yaml_path}: file is empty or contains only comments;"
            " delete the file or add at least one prompt_hash → record entry",
            details={
                "step": "fixture_yaml_empty",
                "fixture_path": str(yaml_path),
                "workflow_step": workflow_step,
            },
        )
    if not isinstance(data, dict):
        raise MockMissError(
            f"malformed fixture file {yaml_path}:"
            " top-level must be a mapping of prompt_hash -> record",
            details={
                "step": "fixture_yaml_shape",
                "fixture_path": str(yaml_path),
                "workflow_step": workflow_step,
            },
        )
    return data


def _ingest_fixture_records(
    yaml_path: Path,
    workflow_step: str,
    data: dict[object, object],
    fixtures: dict[tuple[str, str], _Fixture],
) -> None:
    """Validate each prompt_hash → record entry and insert into `fixtures`."""
    for prompt_hash, record in data.items():
        if not isinstance(prompt_hash, str) or not prompt_hash.startswith(_SHA256_PREFIX):
            raise MockMissError(
                f"malformed fixture key in {yaml_path}:"
                f" '{prompt_hash}' is not a sha256:<hex> string",
                details={
                    "step": "fixture_key_shape",
                    "fixture_path": str(yaml_path),
                    "workflow_step": workflow_step,
                    "key": str(prompt_hash),
                },
            )
        fixtures[(workflow_step, prompt_hash)] = _Fixture.model_validate(record)


def _load_fixtures(fixtures_dir: Path) -> dict[tuple[str, str], _Fixture]:
    """Eager-load all *.yaml fixtures under fixtures_dir. Pure function — fail-loud on errors."""
    _check_fixtures_dir(fixtures_dir)

    fixtures: dict[tuple[str, str], _Fixture] = {}
    seen_stems: dict[str, Path] = {}
    for yaml_path in sorted(fixtures_dir.glob(_FIXTURE_GLOB)):
        workflow_step = yaml_path.stem  # "sdlc-epics" from "sdlc-epics.yaml"

        # Detect filename stem collision (e.g., case-insensitive FS allowing both
        # `Smoke.yaml` and `smoke.yaml`, or two paths with the same Path.stem).
        existing = seen_stems.get(workflow_step)
        if existing is not None:
            raise MockMissError(
                f"duplicate fixture stem {workflow_step!r}:"
                f" both {existing} and {yaml_path} share the same workflow_step",
                details={
                    "step": "fixture_stem_collision",
                    "workflow_step": workflow_step,
                    "first": str(existing),
                    "second": str(yaml_path),
                },
            )
        seen_stems[workflow_step] = yaml_path

        data = _parse_fixture_file(yaml_path, workflow_step)
        _ingest_fixture_records(yaml_path, workflow_step, data, fixtures)
    return fixtures


class MockAIRuntime(AIRuntime):
    """Deterministic mock AIRuntime (Decision C2, Architecture §356, §1062).

    Loads tests/fixtures/mock_responses/*.yaml at construction;
    dispatch keyed by (workflow_step, prompt_hash). NEVER calls Claude or any subprocess.
    """

    def __init__(self, fixtures_dir: Path | str) -> None:
        self.fixtures_dir: Path = Path(fixtures_dir).resolve()
        self._fixtures: dict[tuple[str, str], _Fixture] = _load_fixtures(self.fixtures_dir)

    async def dispatch(self, prompt: str, context: Mapping[str, object]) -> AgentResult:
        """Look up fixture by (workflow_step, prompt_hash); raise MockMissError on miss.

        Mock dispatch is sync-equivalent — `async` is API-shape, not concurrency.
        Real `ClaudeAIRuntime` (Story 2B-1) WILL await subprocess.run via asyncio.to_thread;
        abstraction holds because mock awaits a no-op.
        """
        await asyncio.sleep(0)  # yield control once — abstraction-adequacy: real mocks await
        workflow_step_raw: Any = context.get("workflow_step", "")
        if not isinstance(workflow_step_raw, str):
            raise MockMissError(
                f"context['workflow_step'] must be str, got {type(workflow_step_raw).__name__}",
                details={
                    "step": "workflow_step_type",
                    "workflow_step_type": type(workflow_step_raw).__name__,
                },
            )
        workflow_step = workflow_step_raw
        prompt_hash = _hash_prompt(prompt)
        key = (workflow_step, prompt_hash)
        fixture = self._fixtures.get(key)
        if fixture is None:
            raise MockMissError(
                f"no fixture for (step={workflow_step}, prompt_hash={prompt_hash});"
                f" add a YAML at {self.fixtures_dir}/{workflow_step}.yaml under key {prompt_hash}",
                details={
                    "step": "fixture_lookup",
                    "workflow_step": workflow_step,
                    "prompt_hash": prompt_hash,
                    "fixtures_dir": str(self.fixtures_dir),
                },
            )
        return fixture.as_agent_result()
