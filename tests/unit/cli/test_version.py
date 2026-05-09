"""Unit tests for sdlc.cli.version (AC6.1)."""

from __future__ import annotations

import importlib.metadata

import pytest

import sdlc


@pytest.mark.unit
def test_get_version_returns_canonical_string() -> None:
    from sdlc.cli.version import get_version

    assert get_version() == sdlc.__version__


@pytest.mark.unit
def test_get_version_matches_importlib_metadata() -> None:
    from sdlc.cli.version import get_version

    try:
        pkg_version = importlib.metadata.version("sdlc-framework")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("sdlc-framework not installed as a package — skipping metadata check")
    assert get_version() == pkg_version
