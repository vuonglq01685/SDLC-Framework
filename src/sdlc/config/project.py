from __future__ import annotations

from pathlib import Path
from typing import ClassVar, Final

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from sdlc.config.secrets import sanitize
from sdlc.errors import ConfigError

DEFAULT_PROJECT_YAML: Final[str] = "project.yaml"

# Story 3.3 D1(a): the single adopt-mode auto-accept confidence threshold (integer percent).
# Used both to gate interactive offers (confidence ≥ threshold ⇒ prompt) and to auto-accept
# non-interactively (≥ ⇒ accept; below ⇒ skip+warn). Default 80 auto-includes architecture(85)
# / prd(80, boundary) and excludes research(75) per the Story 3.2 confidence table. The
# canonical default lives here (the lower `config` layer) so `adopt/` imports it without a
# reverse dependency.
DEFAULT_AUTO_ACCEPT_THRESHOLD: Final[int] = 80


class ProjectConfig(BaseModel):
    """Typed wrapper for project.yaml (FR51).

    Schema sources: epics.md:610-613, prd.md:797, architecture.md:337/466/652/752.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=False,
    )

    max_parallel_agents: int = Field(default=4, ge=1, strict=True)
    auto_brainstorm: bool = True
    legacy_code_globs: tuple[str, ...] = Field(default_factory=tuple)
    watchdog_timeout_minutes: int = Field(default=30, ge=1)
    # Story 3.3 D1(a): adopt-mode symlink auto-accept threshold (integer percent, no floats).
    auto_accept_threshold: int = Field(
        default=DEFAULT_AUTO_ACCEPT_THRESHOLD, ge=0, le=100, strict=True
    )


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
    errors = exc.errors()
    first = errors[0]
    loc = first.get("loc", ())
    key = loc[0] if loc else "<unknown>"
    if first.get("type") == "extra_forbidden":
        return ConfigError(
            f"project.yaml unknown key {key!r}",
            details={"path": str(target), "key": str(key)},
        )
    msg = sanitize(str(first.get("msg", "validation failed")))
    safe_errors: list[dict[str, object]] = [
        {
            "type": err.get("type"),
            "loc": list(err.get("loc", ())),
            "msg": sanitize(str(err.get("msg", ""))),
        }
        for err in errors
    ]
    return ConfigError(
        f"project.yaml field {key!r} has wrong type: {msg}",
        details={"path": str(target), "key": str(key), "errors": safe_errors},
    )
