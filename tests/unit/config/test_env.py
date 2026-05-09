from __future__ import annotations

import pytest

from sdlc.config import ENV_EXACT_ALLOWLIST, ENV_PREFIX_ALLOWLIST, read_env
from sdlc.errors import ConfigError


@pytest.mark.unit
class TestReadEnv:
    def test_sdlc_prefix_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SDLC_DEBUG", "1")
        assert read_env("SDLC_DEBUG") == "1"

    def test_claude_prefix_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLAUDE_API_KEY", "sk-abc")
        assert read_env("CLAUDE_API_KEY") == "sk-abc"

    def test_gh_token_exact_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GH_TOKEN", "ghp_xyz")
        assert read_env("GH_TOKEN") == "ghp_xyz"

    def test_home_rejected(self) -> None:
        with pytest.raises(ConfigError) as exc_info:
            read_env("HOME")
        err = exc_info.value
        assert err.code == "ERR_CONFIG"
        assert "HOME" in err.message
        assert "allow-list" in err.message

    def test_path_rejected(self) -> None:
        with pytest.raises(ConfigError):
            read_env("PATH")

    def test_openai_api_key_rejected(self) -> None:
        with pytest.raises(ConfigError) as exc_info:
            read_env("OPENAI_API_KEY")
        err = exc_info.value
        assert "OPENAI_API_KEY" in err.message

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ConfigError):
            read_env("")

    def test_lowercase_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("sdlc_debug", "1")
        with pytest.raises(ConfigError):
            read_env("sdlc_debug")

    def test_allowed_but_unset_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SDLC_NONEXISTENT", raising=False)
        result = read_env("SDLC_NONEXISTENT")
        assert result is None

    def test_env_prefix_allowlist_constant(self) -> None:
        assert ENV_PREFIX_ALLOWLIST == ("SDLC_", "CLAUDE_")

    def test_env_exact_allowlist_constant(self) -> None:
        assert "GH_TOKEN" in ENV_EXACT_ALLOWLIST
        assert "NO_COLOR" in ENV_EXACT_ALLOWLIST

    def test_read_env_allows_no_color(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NO_COLOR", raising=False)
        result = read_env("NO_COLOR")
        assert result is None or isinstance(result, str)

    def test_claude_prefix_allowed_but_unset_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CLAUDE_UNSET_VAR", raising=False)
        result = read_env("CLAUDE_UNSET_VAR")
        assert result is None

    def test_details_include_name(self) -> None:
        with pytest.raises(ConfigError) as exc_info:
            read_env("FORBIDDEN_VAR")
        err = exc_info.value
        assert err.details.get("name") == "FORBIDDEN_VAR"

    def test_bare_prefix_rejected(self) -> None:
        # Bare prefix `SDLC_` (empty suffix) must NOT be treated as allowed.
        with pytest.raises(ConfigError):
            read_env("SDLC_")

    def test_bare_claude_prefix_rejected(self) -> None:
        with pytest.raises(ConfigError):
            read_env("CLAUDE_")

    def test_whitespace_only_name_rejected(self) -> None:
        with pytest.raises(ConfigError):
            read_env("   ")
