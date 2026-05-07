from __future__ import annotations

import sdlc


def test_version_string_is_populated() -> None:
    assert isinstance(sdlc.__version__, str)
    assert sdlc.__version__ != ""
