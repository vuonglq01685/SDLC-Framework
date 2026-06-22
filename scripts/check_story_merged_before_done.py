"""Story merged-before-done + TDD-ordering gate (Epic 3 retro A1).

Runs as a ``commit-msg`` pre-commit hook. The commit-msg stage is chosen
deliberately: it is the one stage that gives the gate BOTH the staged fileset
(via ``git diff --cached``) AND the commit message (argv[0]) — the latter
carries the per-commit ``[tdd-along: ...]`` opt-out.

For every story key that this commit flips to ``done`` in
``sprint-status.yaml`` (index value ``done`` while the HEAD value was not),
two rules are enforced against ``git log`` reachable from HEAD:

  R2 (merged-before-done):
    The story MUST have a per-story ``feat(<E.S>)`` or ``fix(<E.S>)`` commit
    reachable from HEAD. A story whose implementation lives only in the
    working tree, or is squashed under a coarse ``feat(epic-N)`` scope, has no
    such commit — and may not be flipped to ``done``. R2 is NOT waivable.

  R1 (tdd-ordering, per CONTRIBUTING §2 / ADR-026):
    A ``test(<E.S>)`` RED commit MUST precede the first GREEN commit in
    ``git log --reverse``. Waived for a given commit when the message carries
    ``[tdd-along: <reason>]`` (novel-substrate stories where the test API is
    designed in-story, which §2 explicitly permits with justification).

This codifies what the Epic 2B retro commissioned as action A2 but which was
never built; its absence let Epic 3 ship 3.3/3.4 squashed under
``feat(epic-3)`` (no per-story test/feat) and 3.5 with no RED commit, and let
3.7 carry a premature ``review->done`` subject. Grandfathering is automatic:
only stories *newly* flipped to ``done`` in the staged diff are gated, so the
historical done-stories of Epics 1-3 are never re-litigated.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import yaml

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]

# Path (repo-relative, forward-slash) of the status file whose ``done`` flips
# this gate watches. Matches git's path output and the literal used by other
# sprint-status-aware scripts.
SPRINT_STATUS_PATH: Final[str] = "_bmad-output/implementation-artifacts/sprint-status.yaml"

# Per-commit opt-out for R1 (TDD ordering). Requires a non-empty reason so the
# waiver is auditable in git history. R2 is never waivable.
_TDD_ALONG_RE: Final[re.Pattern[str]] = re.compile(r"\[tdd-along:[^\]]+\]")

# A conventional-commit subject: ``<type>(<scope>): <summary>``. We only care
# about the test/feat/fix types and the scope token.
_SUBJECT_RE: Final[re.Pattern[str]] = re.compile(r"^(test|feat|fix)\(([^)]+)\)", re.IGNORECASE)

# A story key looks like ``<epic><...>``: ``3-2-...``, ``4-10-...``,
# ``2a-1-...``, ``1-18-1-...``. Epic/retrospective keys (``epic-3``,
# ``epic-3-retrospective``) do not match the leading-digit shape.
_STORY_KEY_RE: Final[re.Pattern[str]] = re.compile(r"^\d+[a-z]?-\d+")

# A story key has at least ``<epic>-<story>`` segments; a third numeric segment
# denotes a sub-story (``1-18-1`` -> story 1.18, sub-story 1).
_MIN_KEY_SEGMENTS: Final[int] = 2
_SUBSTORY_MIN_SEGMENTS: Final[int] = 3


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    reason: str  # empty when ok


@dataclass(frozen=True)
class StoryVerdict:
    story: str
    has_red: bool
    has_green: bool
    red_before_green: bool


def has_tdd_along_optout(message: str) -> bool:
    """Return True if the commit message carries a ``[tdd-along: ...]`` waiver."""
    return _TDD_ALONG_RE.search(message) is not None


def is_story_key(key: str) -> bool:
    """Return True for real story keys, False for epic/retrospective keys."""
    if "retrospective" in key:
        return False
    return _STORY_KEY_RE.match(key) is not None


def derive_scope_candidates(story_key: str) -> tuple[str, ...]:
    """Map a story key to the commit-scope token(s) it may appear under.

    ``3-2-pass-1-detection`` -> ``("3.2",)``
    ``4-10-auto-brainstorm``  -> ``("4.10",)``
    ``2a-1-workflow-loader``  -> ``("2a.1",)``
    ``1-18-1-cli-trace``      -> ``("1.18", "1.18.1")`` (story 1.18 sub-story 1)
    """
    segments = story_key.split("-")
    if len(segments) < _MIN_KEY_SEGMENTS:
        return ()
    epic, story = segments[0], segments[1]
    candidates = [f"{epic}.{story}"]
    # A purely-numeric third segment is a sub-story number (1-18-1 -> 1.18.1);
    # a textual third segment (3-2-pass-...) is slug text, not a sub-story.
    if len(segments) >= _SUBSTORY_MIN_SEGMENTS and segments[2].isdigit():
        candidates.append(f"{epic}.{story}.{segments[2]}")
    return tuple(candidates)


def parse_development_status(yaml_text: str) -> dict[str, str]:
    """Extract the ``development_status`` map from sprint-status.yaml text.

    Returns an empty dict for empty/blank input or a missing/non-mapping
    ``development_status`` block.
    """
    if not yaml_text.strip():
        return {}
    data = yaml.safe_load(yaml_text) or {}
    status = data.get("development_status", {}) if isinstance(data, Mapping) else {}
    if not isinstance(status, Mapping):
        return {}
    return {str(k): str(v) for k, v in status.items()}


def diff_newly_done(head: Mapping[str, str], staged: Mapping[str, str]) -> list[str]:
    """Return story keys flipped to ``done`` in ``staged`` vs ``head``."""
    newly_done: list[str] = []
    for key, status in staged.items():
        if status != "done":
            continue
        if not is_story_key(key):
            continue
        if head.get(key) != "done":
            newly_done.append(key)
    return newly_done


def _scope_of(subject: str, scopes: Sequence[str]) -> str | None:
    """Return the commit type (test/feat/fix) if the subject's scope matches."""
    match = _SUBJECT_RE.match(subject.strip())
    if match is None:
        return None
    commit_type = match.group(1).lower()
    scope = match.group(2).strip().lower()
    if scope in {candidate.lower() for candidate in scopes}:
        return commit_type
    return None


def classify_story(
    story: str, scopes: Sequence[str], subjects_oldest_first: Sequence[str]
) -> StoryVerdict:
    """Read RED/GREEN presence and ordering from git-log subjects.

    ``subjects_oldest_first`` is the output of ``git log --reverse`` (oldest
    commit first), so a lower index means an earlier commit.
    """
    first_red: int | None = None
    first_green: int | None = None
    for index, subject in enumerate(subjects_oldest_first):
        commit_type = _scope_of(subject, scopes)
        if commit_type == "test" and first_red is None:
            first_red = index
        elif commit_type in ("feat", "fix") and first_green is None:
            first_green = index
    has_red = first_red is not None
    has_green = first_green is not None
    red_before_green = first_red is not None and first_green is not None and first_red < first_green
    return StoryVerdict(story, has_red, has_green, red_before_green)


def validate(
    newly_done: Sequence[str],
    subjects_oldest_first: Sequence[str],
    message: str,
) -> ValidationResult:
    """Apply R2 then R1 to each newly-done story; aggregate failures."""
    opt_out = has_tdd_along_optout(message)
    failures: list[str] = []
    for story in newly_done:
        scopes = derive_scope_candidates(story)
        scope_label = scopes[0] if scopes else story
        verdict = classify_story(story, scopes, subjects_oldest_first)

        if not verdict.has_green:
            failures.append(
                f"{story}: R2 — no per-story `feat({scope_label})`/`fix({scope_label})` "
                "commit reachable from HEAD. The implementation is uncommitted or "
                "squashed under a coarse `epic-*` scope. Commit it under its own story "
                "scope (and merge the branch) before flipping to `done`."
            )
            continue

        if opt_out:
            continue  # R1 waived for this commit; R2 already satisfied above.

        if not verdict.has_red:
            failures.append(
                f"{story}: R1 — found `feat({scope_label})` but no `test({scope_label})` "
                "RED commit. CONTRIBUTING §2 requires tests-first ordering. Add a "
                "tests-first commit, or annotate this flip commit with "
                "`[tdd-along: <reason>]` if the test API is designed in-story."
            )
        elif not verdict.red_before_green:
            failures.append(
                f"{story}: R1 — `test({scope_label})` appears AFTER the first "
                f"`feat({scope_label})`. RED must precede GREEN in "
                "`git log --reverse`."
            )

    if failures:
        return ValidationResult(ok=False, reason="\n".join(failures))
    return ValidationResult(ok=True, reason="")


def _run_git(args: list[str]) -> str | None:
    """Run ``git <args>`` and return stdout, or None on any failure."""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",  # git emits UTF-8; without this the Windows locale
            # (cp1252) mojibakes/raises on em-dash commit subjects and the gate
            # false-passes — the Epic-4 retro A2 cp1252 finding.
            check=False,
            cwd=_REPO_ROOT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _staged_paths() -> list[str]:
    """Return the repo-relative paths git would commit (staged)."""
    out = _run_git(["diff", "--cached", "--name-only"])
    if out is None:
        return []
    return [line for line in out.splitlines() if line.strip()]


def _blob_at_index(path: str) -> str:
    """Return the staged (index) content of ``path``, or '' if absent."""
    out = _run_git(["show", f":{path}"])
    return out if out is not None else ""


def _blob_at_head(path: str) -> str:
    """Return HEAD's content of ``path``, or '' if absent (e.g. new file)."""
    out = _run_git(["show", f"HEAD:{path}"])
    return out if out is not None else ""


def _git_log_subjects() -> list[str]:
    """Return commit subjects reachable from HEAD, oldest first."""
    out = _run_git(["log", "--reverse", "--pretty=%s"])
    if out is None:
        return []
    return out.splitlines()


def main(argv: list[str] | None = None) -> int:
    """CLI entry. Argv: [commit_msg_file_path].

    Exit codes:
      0 — passes (no status flip, no newly-done story, or all rules satisfied)
      1 — R1 or R2 violated for at least one newly-done story
      2 — usage/IO error (no argv, or commit-msg file unreadable)
    """
    if argv is None or len(argv) < 1:
        print(
            "ERROR: expected commit-msg file path as the first argument "
            "(git invokes this hook with that path)",
            file=sys.stderr,
        )
        return 2

    # Fast path: nothing to do unless this commit touches sprint-status.yaml.
    if SPRINT_STATUS_PATH not in _staged_paths():
        return 0

    msg_path = Path(argv[0])
    try:
        message = msg_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        print(f"ERROR: cannot read commit-msg file {msg_path}: {exc}", file=sys.stderr)
        return 2

    head_status = parse_development_status(_blob_at_head(SPRINT_STATUS_PATH))
    staged_status = parse_development_status(_blob_at_index(SPRINT_STATUS_PATH))
    newly_done = diff_newly_done(head_status, staged_status)
    if not newly_done:
        return 0

    result = validate(newly_done, _git_log_subjects(), message)
    if result.ok:
        return 0

    print(
        "BLOCKED by check_story_merged_before_done (CONTRIBUTING §2/§3 · Epic 3 retro action A1)",
        file=sys.stderr,
    )
    print(result.reason, file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
