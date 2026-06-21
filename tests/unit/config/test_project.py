from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.config import ProjectConfig, load_project_config
from sdlc.errors import ConfigError


@pytest.mark.unit
class TestProjectConfig:
    def test_happy_path_all_fields(self, tmp_path: pytest.TempPathFactory) -> None:
        yaml_file = tmp_path / "project.yaml"  # type: ignore[operator]
        content = (
            "max_parallel_agents: 8\nauto_brainstorm: false\n"
            "legacy_code_globs:\n  - src/legacy/**\nwatchdog_timeout_minutes: 60\n"
        )
        yaml_file.write_text(content)
        cfg = load_project_config(yaml_file)
        assert cfg.max_parallel_agents == 8
        assert cfg.auto_brainstorm is False
        assert cfg.legacy_code_globs == ("src/legacy/**",)
        assert cfg.watchdog_timeout_minutes == 60

    def test_empty_yaml_returns_defaults(self, tmp_path: pytest.TempPathFactory) -> None:
        yaml_file = tmp_path / "project.yaml"  # type: ignore[operator]
        yaml_file.write_text("")
        cfg = load_project_config(yaml_file)
        assert cfg == ProjectConfig()

    def test_whitespace_only_yaml_returns_defaults(self, tmp_path: pytest.TempPathFactory) -> None:
        yaml_file = tmp_path / "project.yaml"  # type: ignore[operator]
        yaml_file.write_text("   \n  \n")
        cfg = load_project_config(yaml_file)
        assert cfg == ProjectConfig()

    def test_path_none_missing_file_returns_defaults(
        self, tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)  # type: ignore[arg-type]
        cfg = load_project_config(None)
        assert cfg == ProjectConfig()

    def test_path_none_existing_file_loads_values(
        self, tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        yaml_file = tmp_path / "project.yaml"  # type: ignore[operator]
        yaml_file.write_text("max_parallel_agents: 2\n")
        monkeypatch.chdir(tmp_path)  # type: ignore[arg-type]
        cfg = load_project_config(None)
        assert cfg.max_parallel_agents == 2

    def test_unknown_key_raises_config_error(self, tmp_path: pytest.TempPathFactory) -> None:
        yaml_file = tmp_path / "project.yaml"  # type: ignore[operator]
        yaml_file.write_text("unknown_key: x\nmax_parallel_agents: 4\n")
        with pytest.raises(ConfigError) as exc_info:
            load_project_config(yaml_file)
        err = exc_info.value
        assert err.code == "ERR_CONFIG"
        assert "unknown_key" in err.message
        assert err.details.get("key") == "unknown_key"

    def test_wrong_type_raises_config_error(self, tmp_path: pytest.TempPathFactory) -> None:
        yaml_file = tmp_path / "project.yaml"  # type: ignore[operator]
        yaml_file.write_text("max_parallel_agents: four\n")
        with pytest.raises(ConfigError) as exc_info:
            load_project_config(yaml_file)
        err = exc_info.value
        assert err.code == "ERR_CONFIG"

    def test_malformed_yaml_raises_config_error(self, tmp_path: pytest.TempPathFactory) -> None:
        yaml_file = tmp_path / "project.yaml"  # type: ignore[operator]
        yaml_file.write_text("{[invalid: yaml\n")
        with pytest.raises(ConfigError) as exc_info:
            load_project_config(yaml_file)
        err = exc_info.value
        assert "malformed" in err.message

    def test_frozen_mutation_raises_validation_error(self) -> None:
        cfg = ProjectConfig()
        with pytest.raises(ValidationError):
            cfg.max_parallel_agents = 8  # type: ignore[misc]

    def test_equality(self) -> None:
        assert ProjectConfig() == ProjectConfig()

    def test_hashability(self) -> None:
        cfg = ProjectConfig()
        result = hash(cfg)
        assert isinstance(result, int)

    def test_extra_forbid_config(self) -> None:
        assert ProjectConfig.model_config.get("extra") == "forbid"

    def test_list_to_tuple_coercion(self) -> None:
        cfg = ProjectConfig(legacy_code_globs=["a", "b"])  # type: ignore[arg-type]
        assert cfg.legacy_code_globs == ("a", "b")
        assert isinstance(cfg.legacy_code_globs, tuple)

    def test_top_level_not_dict_raises_config_error(self, tmp_path: pytest.TempPathFactory) -> None:
        yaml_file = tmp_path / "project.yaml"  # type: ignore[operator]
        yaml_file.write_text("- item1\n- item2\n")
        with pytest.raises(ConfigError) as exc_info:
            load_project_config(yaml_file)
        err = exc_info.value
        assert "mapping" in err.message

    def test_yaml_comment_only_returns_defaults(self, tmp_path: pytest.TempPathFactory) -> None:
        yaml_file = tmp_path / "project.yaml"  # type: ignore[operator]
        yaml_file.write_text("# just a comment\n")
        cfg = load_project_config(yaml_file)
        assert cfg == ProjectConfig()

    def test_defaults_values(self) -> None:
        cfg = ProjectConfig()
        assert cfg.max_parallel_agents == 4
        assert cfg.auto_brainstorm is True
        assert cfg.legacy_code_globs == ()
        assert cfg.watchdog_timeout_minutes == 30

    def test_max_parallel_agents_ge1_constraint(self) -> None:
        with pytest.raises(ValidationError):
            ProjectConfig(max_parallel_agents=0)

    def test_watchdog_timeout_gt0_constraint(self) -> None:
        with pytest.raises(ValidationError):
            ProjectConfig(watchdog_timeout_minutes=0)

    def test_watchdog_timeout_rejects_negative(self) -> None:
        with pytest.raises(ValidationError):
            ProjectConfig(watchdog_timeout_minutes=-1)

    def test_watchdog_timeout_accepts_fractional(self) -> None:
        cfg = ProjectConfig(watchdog_timeout_minutes=0.05)
        assert cfg.watchdog_timeout_minutes == 0.05

    def test_watchdog_timeout_non_numeric_rejected_via_loader(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        yaml_file = tmp_path / "project.yaml"  # type: ignore[operator]
        yaml_file.write_text("watchdog_timeout_minutes: foo\n")
        with pytest.raises(ConfigError):
            load_project_config(yaml_file)

    def test_watchdog_timeout_strict_rejects_bool(self) -> None:
        # strict=True must reject YAML booleans: `true` would otherwise coerce to
        # 1.0 (bool is an int subclass) and silently arm a 1-minute watchdog (AC2/C2).
        with pytest.raises(ValidationError):
            ProjectConfig(watchdog_timeout_minutes=True)

    def test_watchdog_timeout_yaml_bool_rejected_via_loader(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        yaml_file = tmp_path / "project.yaml"  # type: ignore[operator]
        yaml_file.write_text("watchdog_timeout_minutes: true\n")
        with pytest.raises(ConfigError):
            load_project_config(yaml_file)

    def test_watchdog_timeout_strict_rejects_quoted_number(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        # A quoted YAML scalar is a string; strict=True must not coerce "4" -> 4.0.
        yaml_file = tmp_path / "project.yaml"  # type: ignore[operator]
        yaml_file.write_text('watchdog_timeout_minutes: "4"\n')
        with pytest.raises(ConfigError):
            load_project_config(yaml_file)

    def test_watchdog_timeout_yaml_loads_fraction(self, tmp_path: pytest.TempPathFactory) -> None:
        yaml_file = tmp_path / "project.yaml"  # type: ignore[operator]
        yaml_file.write_text("watchdog_timeout_minutes: 0.05\n")
        cfg = load_project_config(yaml_file)
        assert cfg.watchdog_timeout_minutes == 0.05

    def test_max_parallel_agents_strict_rejects_float(self) -> None:
        # strict=True must reject float values (no silent rounding 4.5 → 4).
        with pytest.raises(ValidationError):
            ProjectConfig(max_parallel_agents=4.5)  # type: ignore[arg-type]

    def test_max_parallel_agents_strict_rejects_string(self) -> None:
        with pytest.raises(ValidationError):
            ProjectConfig(max_parallel_agents="4")  # type: ignore[arg-type]

    def test_max_parallel_agents_strict_rejects_yaml_quoted_int(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        yaml_file = tmp_path / "project.yaml"  # type: ignore[operator]
        yaml_file.write_text('max_parallel_agents: "4"\n')
        with pytest.raises(ConfigError) as exc_info:
            load_project_config(yaml_file)
        assert "wrong type" in exc_info.value.message

    def test_wrong_type_message_uses_wrong_type_phrasing(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        yaml_file = tmp_path / "project.yaml"  # type: ignore[operator]
        yaml_file.write_text("max_parallel_agents: four\n")
        with pytest.raises(ConfigError) as exc_info:
            load_project_config(yaml_file)
        assert "wrong type" in exc_info.value.message
        # details["key"] (not "field") for consistency with extra_forbidden branch.
        assert exc_info.value.details.get("key") == "max_parallel_agents"

    def test_wrong_type_errors_are_safe_subset(self, tmp_path: pytest.TempPathFactory) -> None:
        yaml_file = tmp_path / "project.yaml"  # type: ignore[operator]
        yaml_file.write_text("max_parallel_agents: four\n")
        with pytest.raises(ConfigError) as exc_info:
            load_project_config(yaml_file)
        errors = exc_info.value.details.get("errors")
        assert isinstance(errors, list)
        for entry in errors:
            assert isinstance(entry, dict)
            # Only safe keys; no `input`/`url` leak from pydantic.
            assert set(entry.keys()) == {"type", "loc", "msg"}
