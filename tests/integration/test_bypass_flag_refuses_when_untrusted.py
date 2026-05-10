"""Integration tests for bypass validation vs 2A.5 trust surface (AC6, Story 2A.4 Task 8.3)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sdlc.cli._bypass import validate_bypass_request
from sdlc.errors import HookError
from sdlc.hooks._hash_store import HOOKS_ROOT_LABEL
from sdlc.hooks.tampering import compute_hook_hashes


def _init_trust_store(state_root: Path, hooks_root: Path) -> None:
    """Write a valid hook-hashes.json to mark trust as initialized."""
    state_root.mkdir(parents=True, exist_ok=True)
    hooks_root.mkdir(parents=True, exist_ok=True)
    hashes = compute_hook_hashes(hooks_root)
    store = {
        "schema_version": 1,
        "hooks_root": HOOKS_ROOT_LABEL,  # must be the canonical label, not a real path
        "hashes": hashes,
        "trusted_at": "2026-05-10T00:00:00.000Z",
    }
    (state_root / "hook-hashes.json").write_text(json.dumps(store))


@pytest.mark.integration
class TestBypassRefusesWhenUntrusted:
    def test_uninitialized_no_hash_file_raises(self, tmp_path) -> None:
        """No hook-hashes.json → detect_tampering returns uninitialized → bypass refused."""
        repo_root = tmp_path
        state_root = repo_root / ".claude" / "state"
        state_root.mkdir(parents=True, exist_ok=True)
        # No hook-hashes.json — uninitialized

        with pytest.raises(HookError, match="trust"):
            validate_bypass_request("valid justification text", repo_root=repo_root)

    def test_corrupted_hash_file_raises(self, tmp_path) -> None:
        """Corrupted hook-hashes.json → detect_tampering returns corrupted → bypass refused."""
        repo_root = tmp_path
        state_root = repo_root / ".claude" / "state"
        state_root.mkdir(parents=True, exist_ok=True)
        (state_root / "hook-hashes.json").write_text("{ invalid json [")

        with pytest.raises(HookError, match="trust"):
            validate_bypass_request("valid justification text", repo_root=repo_root)

    def test_clean_trust_passes(self, tmp_path) -> None:
        """Clean trust store → bypass is allowed."""
        repo_root = tmp_path
        state_root = repo_root / ".claude" / "state"
        hooks_root = repo_root / ".claude" / "hooks"
        _init_trust_store(state_root, hooks_root)

        result = validate_bypass_request("valid justification text", repo_root=repo_root)
        assert result is None

    def test_tampered_trust_still_allows(self, tmp_path) -> None:
        """Tampered is advisory-only in v1 — bypass is still allowed."""
        repo_root = tmp_path
        state_root = repo_root / ".claude" / "state"
        hooks_root = repo_root / ".claude" / "hooks"
        _init_trust_store(state_root, hooks_root)

        # Now add an extra hook file to cause tampering
        hooks_root.mkdir(parents=True, exist_ok=True)
        (hooks_root / "extra_hook.py").write_text("# extra hook\n")

        result = validate_bypass_request("valid justification text", repo_root=repo_root)
        assert result is None
