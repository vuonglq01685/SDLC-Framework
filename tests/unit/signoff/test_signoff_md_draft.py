"""Unit tests for _SignoffMdDraft reader (AC2, Story 2A.7)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_VALID_HASH = "sha256:" + "a" * 64
_TS = "2026-05-10T11:00:00.000Z"


def _frontmatter_draft(phase: int = 1, approved: bool = False) -> str:
    return textwrap.dedent(f"""\
        ---
        schema_version: 1
        phase: {phase}
        artifacts:
          - path: 0{phase}-Requirement/PRODUCT.md
            hash: {_VALID_HASH}
        approved: {str(approved).lower()}
        approved_by: null
        approved_at: null
        drafted_at: {_TS}
        ---

        # Signoff Draft Phase {phase}

        This draft covers the phase {phase} artifacts.
    """)


def _fenced_draft(phase: int = 1, approved: bool = False) -> str:
    return textwrap.dedent(f"""\
        # Signoff Draft Phase {phase}

        ```signoff
        schema_version: 1
        phase: {phase}
        artifacts:
          - path: 0{phase}-Requirement/PRODUCT.md
            hash: {_VALID_HASH}
        approved: {str(approved).lower()}
        approved_by: null
        approved_at: null
        drafted_at: {_TS}
        ```

        Artifact list follows.
    """)


# ---------------------------------------------------------------------------
# read_signoff_md_draft
# ---------------------------------------------------------------------------


def test_read_draft_frontmatter_form(tmp_path: Path) -> None:
    from sdlc.signoff.records import read_signoff_md_draft

    f = tmp_path / "SIGNOFF.md"
    f.write_text(_frontmatter_draft(), encoding="utf-8")
    draft = read_signoff_md_draft(f)
    assert draft.phase == 1
    assert draft.approved is False


def test_read_draft_fenced_form(tmp_path: Path) -> None:
    from sdlc.signoff.records import read_signoff_md_draft

    f = tmp_path / "SIGNOFF.md"
    f.write_text(_fenced_draft(), encoding="utf-8")
    draft = read_signoff_md_draft(f)
    assert draft.phase == 1
    assert len(draft.artifacts) == 1


def test_read_draft_approved_true(tmp_path: Path) -> None:
    from sdlc.signoff.records import read_signoff_md_draft

    f = tmp_path / "SIGNOFF.md"
    f.write_text(_frontmatter_draft(approved=True), encoding="utf-8")
    draft = read_signoff_md_draft(f)
    assert draft.approved is True


def test_read_draft_malformed_yaml_raises(tmp_path: Path) -> None:
    from sdlc.errors import SignoffError
    from sdlc.signoff.records import read_signoff_md_draft

    f = tmp_path / "SIGNOFF.md"
    f.write_text("---\n}{bad yaml\n---\n", encoding="utf-8")
    with pytest.raises(SignoffError, match="malformed"):
        read_signoff_md_draft(f)


def test_read_draft_schema_invalid_raises(tmp_path: Path) -> None:
    from sdlc.errors import SignoffError
    from sdlc.signoff.records import read_signoff_md_draft

    bad = "---\nschema_version: 1\nphase: 1\n---\n"
    f = tmp_path / "SIGNOFF.md"
    f.write_text(bad, encoding="utf-8")
    with pytest.raises(SignoffError, match="malformed"):
        read_signoff_md_draft(f)


def test_read_draft_rejects_absolute_artifact_path(tmp_path: Path) -> None:
    from sdlc.errors import SignoffError
    from sdlc.signoff.records import read_signoff_md_draft

    content = textwrap.dedent(f"""\
        ---
        schema_version: 1
        phase: 1
        artifacts:
          - path: /absolute/path.md
            hash: {_VALID_HASH}
        approved: false
        approved_by: null
        approved_at: null
        drafted_at: {_TS}
        ---
    """)
    f = tmp_path / "SIGNOFF.md"
    f.write_text(content, encoding="utf-8")
    with pytest.raises(SignoffError, match="repo-relative"):
        read_signoff_md_draft(f)


def test_read_draft_rejects_dotdot_traversal(tmp_path: Path) -> None:
    from sdlc.errors import SignoffError
    from sdlc.signoff.records import read_signoff_md_draft

    content = textwrap.dedent(f"""\
        ---
        schema_version: 1
        phase: 1
        artifacts:
          - path: ../outside/file.md
            hash: {_VALID_HASH}
        approved: false
        approved_by: null
        approved_at: null
        drafted_at: {_TS}
        ---
    """)
    f = tmp_path / "SIGNOFF.md"
    f.write_text(content, encoding="utf-8")
    with pytest.raises(SignoffError, match="repo-relative"):
        read_signoff_md_draft(f)


def test_draft_is_private_model() -> None:
    """_SignoffMdDraft is NOT exported from sdlc.signoff or sdlc.contracts."""
    import sdlc.signoff as signoff_pkg

    assert not hasattr(signoff_pkg, "_SignoffMdDraft"), "_SignoffMdDraft must not be public"

    try:
        import sdlc.contracts as contracts_pkg
        assert not hasattr(contracts_pkg, "_SignoffMdDraft"), "_SignoffMdDraft must not be in contracts"
    except ImportError:
        pass
