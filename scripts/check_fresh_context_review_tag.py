"""Fresh-context review tag gate (Epic 2A retro action A2, ADR-026 §4).

Runs as a ``commit-msg`` pre-commit hook. Enforces two rules:

  R1 (tag-required-when-review-commit):
    If the commit message body matches review-trigger keywords
    (``code-review``, ``chunked review``, ``review patches``,
    ``apply review``, ``Round-2 review``), the message MUST also
    contain the literal tag ``[fresh-context-review]``.

  R2 (review-commits-must-not-modify-src):
    If the message carries ``[fresh-context-review]``, the staged
    fileset MUST NOT contain any ``src/`` path. Reviews land tests,
    docs, deferred-work, and sprint-status updates — never new
    implementation. Implementation lives in a separate ``feat`` or
    ``fix`` commit committed in an earlier (now-pushed) session.

Skeleton only — implementation lands in C7 GREEN step.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]

FRESH_CONTEXT_TAG: Final[str] = "[fresh-context-review]"

# Trigger phrases that mark a commit as a code-review commit. Case-insensitive
# substring match. Tuned to catch the canonical bmad-code-review subjects used
# across Epic 2A (e.g. "chore(2A.18): code-review patches applied").
_REVIEW_TRIGGER_PHRASES: Final[tuple[str, ...]] = (
    "code-review",
    "code review",
    "chunked review",
    "review patches applied",
    "apply review",
    "round-2 review",
    "round 2 review",
    "bmad-code-review",
)

# Path prefixes whose modification under a [fresh-context-review] commit is
# disallowed (R2). Anything else — tests/, docs/, _bmad-output/, scripts/,
# CONTRIBUTING.md, README.md, ADRs — is fair game during review.
_DISALLOWED_PREFIXES_UNDER_REVIEW: Final[tuple[str, ...]] = ("src/",)


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    reason: str  # empty when ok


def detect_review_keywords(message: str) -> bool:
    """Return True if the commit message matches a review-trigger phrase."""
    raise NotImplementedError("C7 GREEN")


def has_fresh_context_tag(message: str) -> bool:
    """Return True if the commit message contains the fresh-context tag."""
    raise NotImplementedError("C7 GREEN")


def partition_staged(files: list[str]) -> tuple[list[str], list[str]]:
    """Split staged files into ``(allowed, disallowed_under_review)`` lists."""
    raise NotImplementedError("C7 GREEN")


def validate(message: str, staged_files: list[str]) -> ValidationResult:
    """Apply R1 + R2 and return a structured pass/fail."""
    raise NotImplementedError("C7 GREEN")


def main(argv: list[str] | None = None) -> int:
    """CLI entry. Argv: [commit_msg_file_path].

    Exit codes:
      0 — passes (either not a review commit, or correctly tagged with no
          src/ modifications)
      1 — R1 or R2 violated (missing tag, or src/ in tagged commit)
      2 — IO error (commit message file missing/unreadable)
    """
    raise NotImplementedError("C7 GREEN")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
