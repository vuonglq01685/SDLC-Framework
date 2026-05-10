"""WorkflowRegistry — eager package-data loader (Story 2A.1, AC6).

WorkflowRegistry is the intended entrypoint for engine code that needs to
enumerate workflows. Direct calls to ``load_workflow`` outside of ``workflows/``
and tests are a code-review-blocking pattern (Architecture §1063).

The registry walks ``workflows_dir`` for both ``*.yaml`` and ``*.yml`` files in
sorted lexical order, skipping hidden dotfiles. It calls ``load_workflow`` then
``validate_workflow`` on each file and freezes the result. Any failure aborts
construction immediately; no partial registry state is exposed.

**Strict duplicate semantics (AC6, intentional):** a duplicate ``slash_command``
across two YAML files raises ``WorkflowError`` regardless of file content
identity. Slash-command comparison is normalized (whitespace-stripped,
case-folded) so ``/Foo`` and ``/foo`` collide. This is intentional even for
copy-rename refactors inside a single PR — the registry's job is to surface
ambiguity at load time. Mirrors the duplicate-stem detection idiom from
``src/sdlc/runtime/mock.py:191-218``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

from sdlc.contracts.workflow_spec import WorkflowSpec
from sdlc.errors import WorkflowError
from sdlc.workflows.loader import load_workflow
from sdlc.workflows.static_check import validate_workflow


def _normalize_slash_command(cmd: str) -> str:
    """Normalize a slash-command for byte-stable duplicate detection."""
    return cmd.strip().casefold()


def _collect_workflow_paths(workflows_dir: Path) -> tuple[Path, ...]:
    """Return YAML file paths in sorted lexical order, skipping hidden dotfiles."""
    seen: set[Path] = set()
    for ext in ("*.yaml", "*.yml"):
        for p in workflows_dir.glob(ext):
            if p.name.startswith("."):
                # Hidden / dotfile YAML is excluded to avoid surprise registration.
                continue
            if not p.is_file():
                continue
            seen.add(p)
    return tuple(sorted(seen))


@dataclass(frozen=True)
class WorkflowRegistry:
    """Immutable registry mapping slash_command → WorkflowSpec.

    Construct via :meth:`WorkflowRegistry.load` (the public factory). Direct
    construction is only intended for empty-registry sentinels and tests; the
    ``__post_init__`` validator ensures ``_workflows`` is always a frozen
    ``MappingProxyType`` so callers cannot mutate the registry through field
    access.
    """

    _workflows: MappingProxyType[str, WorkflowSpec] = field(
        default_factory=lambda: MappingProxyType({}),
    )

    def __post_init__(self) -> None:
        if not isinstance(self._workflows, MappingProxyType):
            # Defensive: a non-proxy mapping would mean callers can mutate the
            # registry contents post-construction. The factory always wraps in
            # MappingProxyType, but a hand-built dataclass call could bypass.
            raise WorkflowError(
                "WorkflowRegistry._workflows must be a MappingProxyType; "
                "use WorkflowRegistry.load() to construct.",
                details={"actual_type": type(self._workflows).__name__},
            )

    @classmethod
    def load(cls, workflows_dir: Path) -> WorkflowRegistry:
        """Eagerly load all *.yaml / *.yml files from workflows_dir.

        Args:
            workflows_dir: Directory containing workflow YAML files.

        Returns:
            A frozen WorkflowRegistry instance.

        Raises:
            WorkflowError: On any load/validate failure or duplicate slash_command.
        """
        collected: dict[str, WorkflowSpec] = {}
        path_by_command: dict[str, Path] = {}
        norm_to_command: dict[str, str] = {}

        for yaml_path in _collect_workflow_paths(workflows_dir):
            spec = load_workflow(yaml_path)
            validate_workflow(spec)

            cmd = spec.slash_command
            norm = _normalize_slash_command(cmd)
            if norm in norm_to_command:
                first_cmd = norm_to_command[norm]
                raise WorkflowError(
                    f"duplicate slash_command {cmd!r}: "
                    f"{path_by_command[first_cmd]} and {yaml_path}",
                    details={
                        "slash_command": cmd,
                        "duplicate_normalized": norm,
                        "first_slash_command": first_cmd,
                        "path1": str(path_by_command[first_cmd]),
                        "path2": str(yaml_path),
                    },
                )
            collected[cmd] = spec
            path_by_command[cmd] = yaml_path
            norm_to_command[norm] = cmd

        return cls(_workflows=MappingProxyType(collected))

    def get(self, slash_command: str) -> WorkflowSpec:
        """Return the WorkflowSpec for slash_command.

        Raises:
            WorkflowError: if slash_command is not registered.
        """
        try:
            return self._workflows[slash_command]
        except KeyError:
            raise WorkflowError(
                f"unknown slash_command {slash_command!r}",
                details={"slash_command": slash_command},
            ) from None

    def list(self) -> tuple[WorkflowSpec, ...]:
        """Return all registered workflows sorted by slash_command.

        Sort key is the slash_command string explicitly (not ``items()`` whose
        fallback comparison would compare ``WorkflowSpec`` instances on key
        collision and raise ``TypeError``).
        """
        return tuple(self._workflows[k] for k in sorted(self._workflows.keys()))
