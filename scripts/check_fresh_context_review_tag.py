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
"""

from __future__ import annotations

import subprocess
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
    lower = message.lower()
    return any(phrase in lower for phrase in _REVIEW_TRIGGER_PHRASES)


def has_fresh_context_tag(message: str) -> bool:
    """Return True if the commit message contains the fresh-context tag.

    Tag match is byte-exact (case-sensitive). Capitalisation drift would
    weaken the audit signal, so ``[Fresh-Context-Review]`` does NOT count.
    """
    return FRESH_CONTEXT_TAG in message


def partition_staged(files: list[str]) -> tuple[list[str], list[str]]:
    """Split staged files into ``(allowed, disallowed_under_review)`` lists."""
    allowed: list[str] = []
    disallowed: list[str] = []
    for path in files:
        if any(path.startswith(prefix) for prefix in _DISALLOWED_PREFIXES_UNDER_REVIEW):
            disallowed.append(path)
        else:
            allowed.append(path)
    return allowed, disallowed


def validate(message: str, staged_files: list[str]) -> ValidationResult:
    """Apply R1 + R2 and return a structured pass/fail."""
    is_review_commit = detect_review_keywords(message)
    has_tag = has_fresh_context_tag(message)

    # R1 — review-keyword commits MUST carry the tag.
    if is_review_commit and not has_tag:
        return ValidationResult(
            ok=False,
            reason=(
                "R1: commit message contains review-trigger keywords but is "
                f"missing the {FRESH_CONTEXT_TAG} tag. Per ADR-026 §4, "
                "code-review commits MUST attest fresh-context review by "
                "carrying the tag. Add it to the commit subject or body."
            ),
        )

    # R2 — tagged commits MUST NOT touch src/.
    if has_tag:
        _allowed, disallowed = partition_staged(staged_files)
        if disallowed:
            offenders = ", ".join(disallowed)
            return ValidationResult(
                ok=False,
                reason=(
                    f"R2: {FRESH_CONTEXT_TAG} commits MUST NOT modify src/ "
                    f"files. Offending: {offenders}. Move implementation "
                    "changes into a separate feat/fix commit."
                ),
            )

    return ValidationResult(ok=True, reason="")


def _read_staged_files() -> list[str]:
    """Return the staged-file paths git would commit, or [] on git failure."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    """CLI entry. Argv: [commit_msg_file_path].

    Exit codes:
      0 — passes (either not a review commit, or correctly tagged with no
          src/ modifications)
      1 — R1 or R2 violated
      2 — IO error (commit message file missing/unreadable, no argv)
    """
    if argv is None or len(argv) < 1:
        print(
            "ERROR: expected commit-msg file path as the first argument "
            "(git invokes this hook with that path)",
            file=sys.stderr,
        )
        return 2

    msg_path = Path(argv[0])
    try:
        message = msg_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        print(f"ERROR: cannot read commit-msg file {msg_path}: {exc}", file=sys.stderr)
        return 2

    staged_files = _read_staged_files()
    result = validate(message, staged_files)

    if result.ok:
        return 0

    print(
        "BLOCKED by check_fresh_context_review_tag (CONTRIBUTING §4 / ADR-026 §4)",
        file=sys.stderr,
    )
    print(f"  {result.reason}", file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
