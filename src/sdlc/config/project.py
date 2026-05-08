from __future__ import annotations

from pathlib import Path
from typing import ClassVar, Final

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from sdlc.errors import ConfigError

DEFAULT_PROJECT_YAML: Final[str] = "project.yaml"


class ProjectConfig(BaseModel):
    """Typed wrapper for project.yaml (FR51).

    Schema sources: epics.md:610-613, prd.md:797, architecture.md:337/466/652/752.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=False,
    )

    max_parallel_agents: int = Field(default=4, ge=1)
    auto_brainstorm: bool = True
    legacy_code_globs: tuple[str, ...] = Field(default_factory=tuple)
    watchdog_timeout_minutes: int = Field(default=30, ge=1)


def load_project_config(path: Path | None = None) -> ProjectConfig:
    """Load ``project.yaml`` from ``path`` (default: <cwd>/project.yaml).

    Behaviour:
    - Missing file → return ProjectConfig() defaults.
    - Empty/whitespace-only file → return ProjectConfig() defaults.
    - Malformed YAML → ConfigError.
    - Unknown key → ConfigError naming the key.
    - Wrong type → ConfigError wrapping pydantic ValidationError.
    """
    target = Path(path) if path is not None else Path.cwd() / DEFAULT_PROJECT_YAML
    if not target.exists():
        return ProjectConfig()
    raw = target.read_text(encoding="utf-8")
    if not raw.strip():
        return ProjectConfig()
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ConfigError(
            f"project.yaml malformed: {exc}",
            details={"path": str(target)},
        ) from exc
    if data is None:
        return ProjectConfig()
    if not isinstance(data, dict):
        raise ConfigError(
            "project.yaml must be a mapping at top level",
            details={"path": str(target), "got_type": type(data).__name__},
        )
    try:
        return ProjectConfig(**data)
    except ValidationError as exc:
        raise _wrap_validation_error(exc, target) from exc


def _wrap_validation_error(exc: ValidationError, target: Path) -> ConfigError:
    first = exc.errors()[0]
    loc = first.get("loc", ())
    key = loc[0] if loc else "<unknown>"
    if first.get("type") == "extra_forbidden":
        return ConfigError(
            f"project.yaml unknown key {key!r}",
            details={"path": str(target), "key": str(key)},
        )
    return ConfigError(
        f"project.yaml field {key!r} invalid: {first.get('msg', 'validation failed')}",
        details={"path": str(target), "field": str(key), "errors": exc.errors()},
    )
