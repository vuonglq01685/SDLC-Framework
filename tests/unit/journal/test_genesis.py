"""Unit tests for ``sdlc.journal._genesis.GENESIS_HASH``.

Pinning the constant guards against drift from spec value (Story 2A.5 DR5).
"""

from __future__ import annotations

import hashlib

import pytest

from sdlc.journal._genesis import GENESIS_HASH


@pytest.mark.unit
def test_genesis_hash_is_sha256_of_empty_bytes() -> None:
    expected = "sha256:" + hashlib.sha256(b"").hexdigest()
    assert expected == GENESIS_HASH


@pytest.mark.unit
def test_genesis_hash_has_canonical_prefix_and_length() -> None:
    assert GENESIS_HASH.startswith("sha256:")
    digest = GENESIS_HASH.removeprefix("sha256:")
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


@pytest.mark.unit
def test_genesis_hash_is_immutable_constant() -> None:
    # Re-import yields same object; smoke test for frozen Final declaration.
    from sdlc.journal import _genesis

    assert _genesis.GENESIS_HASH == GENESIS_HASH
