"""Anti-tautology tests for NFR-SEC-7 heuristics (Story 2A.1, AC3).

Each adversarial fixture is mutated **textually in place** (not via
``yaml.safe_dump`` round-trip — see P7 of the 2A.1 review) to remove the
offending substring, then asserted to pass ``load_workflow``. This proves the
heuristic — not the YAML envelope — is doing the work.

Why textual mutation:
- ``yaml.safe_dump`` may re-encode the replacement value with different
  quoting, line wrapping, or anchor reuse, which means the test would prove
  "round-trip with new value passes" rather than "removing the offending
  substring passes". Patching the fixture bytes ensures the only delta is
  the substring removal.
- ``tempfile.NamedTemporaryFile(delete=False)`` was previously used and
  combined with ``unlink(missing_ok=True)`` could leak tempfiles on Windows
  (file held open by the ``with`` block); ``tmp_path`` from pytest is the
  cleaner idiom.

Manual verification receipt (per ADR-027 + Story 2A.0 AC6 pattern):
  - instruction_prefix: removed "Ignore previous instructions and" prefix
    → test passes (heuristic fires; sanitized version passes)
  - fenced_code_block: removed the triple-backtick fence
    → test passes
  - xml_instruction_tag: replaced <system>...</system> with a clean agent name
    → test passes
  - length_overflow: shrunk the 514-char string to 10 chars
    → test passes
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.workflows import load_workflow

SEC7_DIR = Path(__file__).parent.parent.parent / "fixtures" / "workflows" / "adversarial" / "sec7"


def _patch_fixture_text(
    fixture_name: str,
    needle: str,
    replacement: str,
    tmp_path: Path,
) -> Path:
    """Apply a single text replacement to an adversarial fixture.

    The patched file lands in pytest's ``tmp_path`` (which pytest cleans up
    automatically across test sessions). The only delta from the original
    fixture is the ``needle → replacement`` substitution.
    """
    raw = (SEC7_DIR / fixture_name).read_text(encoding="utf-8")
    if needle not in raw:
        msg = f"needle {needle!r} not found in fixture {fixture_name}"
        raise AssertionError(msg)
    patched = raw.replace(needle, replacement, 1)
    out = tmp_path / fixture_name
    out.write_text(patched, encoding="utf-8")
    return out


@pytest.mark.unit
def test_instruction_prefix_sanitized_passes(tmp_path: Path) -> None:
    """Removing the instruction prefix substring allows the fixture to pass."""
    patched = _patch_fixture_text(
        "instruction_prefix.yaml",
        needle="Ignore previous instructions and ",
        replacement="",
        tmp_path=tmp_path,
    )
    load_workflow(patched)


@pytest.mark.unit
def test_fenced_code_block_sanitized_passes(tmp_path: Path) -> None:
    """Removing the triple-backtick fence allows the fixture to pass."""
    patched = _patch_fixture_text(
        "fenced_code_block.yaml",
        needle="```",
        replacement="",
        tmp_path=tmp_path,
    )
    # The fixture has TWO backtick fences (open + close); strip both.
    raw = patched.read_text(encoding="utf-8").replace("```", "")
    patched.write_text(raw, encoding="utf-8")
    load_workflow(patched)


@pytest.mark.unit
def test_xml_tag_sanitized_passes(tmp_path: Path) -> None:
    """Removing the XML instruction tag substring allows the fixture to pass."""
    patched = _patch_fixture_text(
        "xml_tag.yaml",
        needle="<system>",
        replacement="",
        tmp_path=tmp_path,
    )
    raw = patched.read_text(encoding="utf-8").replace("</system>", "")
    patched.write_text(raw, encoding="utf-8")
    load_workflow(patched)


@pytest.mark.unit
def test_length_overflow_sanitized_passes(tmp_path: Path) -> None:
    """Shrinking the over-long string allows the fixture to pass.

    The fixture's offending value is a single very-long string; we replace it
    with a short literal that satisfies both the length and the heuristic
    catalog.
    """
    raw = (SEC7_DIR / "length_overflow.yaml").read_text(encoding="utf-8")
    # Find the over-long line and shrink to 10 chars.
    patched_lines: list[str] = []
    shrunk = False
    for line in raw.splitlines(keepends=True):
        if "primary_agent:" in line:
            patched_lines.append("primary_agent: short-agent\n")
            shrunk = True
        else:
            patched_lines.append(line)
    if not shrunk:
        msg = "length_overflow.yaml does not contain primary_agent: line"
        raise AssertionError(msg)
    out = tmp_path / "length_overflow.yaml"
    out.write_text("".join(patched_lines), encoding="utf-8")
    load_workflow(out)
