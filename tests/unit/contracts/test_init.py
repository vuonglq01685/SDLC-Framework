from __future__ import annotations

import pytest

import sdlc.contracts as contracts_pkg
from sdlc.contracts import (
    AdoptedSymlinks,
    AdoptReport,
    HookPayload,
    JournalEntry,
    ResumeToken,
    SpecialistFrontmatter,
    WorkflowSpec,
)


@pytest.mark.unit
class TestContractsPackageNamespace:
    def test_all_tuple_matches_spec(self) -> None:
        # Locks-in the AC7 semantic order: prototype JournalEntry first, then
        # the other four per Architecture §1238 enumeration, then AdoptReport
        # (6th locked contract — Story 3.1) + AdoptedSymlinks (7th — Story 3.3).
        assert contracts_pkg.__all__ == (
            "JournalEntry",
            "ResumeToken",
            "HookPayload",
            "SpecialistFrontmatter",
            "WorkflowSpec",
            "AdoptReport",
            "AdoptedSymlinks",
        )

    def test_all_names_are_resolvable(self) -> None:
        for name in contracts_pkg.__all__:
            assert hasattr(contracts_pkg, name), f"{name} not present in package"

    def test_re_exports_resolve_to_correct_classes(self) -> None:
        assert contracts_pkg.JournalEntry is JournalEntry
        assert contracts_pkg.ResumeToken is ResumeToken
        assert contracts_pkg.HookPayload is HookPayload
        assert contracts_pkg.SpecialistFrontmatter is SpecialistFrontmatter
        assert contracts_pkg.WorkflowSpec is WorkflowSpec
        assert contracts_pkg.AdoptReport is AdoptReport
        assert contracts_pkg.AdoptedSymlinks is AdoptedSymlinks
