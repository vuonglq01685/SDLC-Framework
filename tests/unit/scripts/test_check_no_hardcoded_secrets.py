from __future__ import annotations

from pathlib import Path

import pytest

import check_no_hardcoded_secrets as guard

SK_KEY = "sk-abc123def456ghi789jkl012mno345pq"


@pytest.mark.unit
class TestScanFile:
    def test_clean_file_passes(self, tmp_path: Path) -> None:
        target = tmp_path / "clean.py"
        target.write_text('x = "hello"\n')
        assert guard._scan_file(target) == []

    def test_secret_in_file_flagged(self, tmp_path: Path) -> None:
        target = tmp_path / "leak.py"
        target.write_text(f'TOKEN = "{SK_KEY}"\n')
        violations = guard._scan_file(target)
        assert len(violations) == 1
        lineno, _, pattern = violations[0]
        assert lineno == 1
        assert "sk-" in pattern

    def test_noqa_with_justification_suppresses(self, tmp_path: Path) -> None:
        target = tmp_path / "ok.py"
        target.write_text(
            f'TOKEN = "{SK_KEY}"  # noqa: secret -- legacy fixture for replay tests\n'
        )
        assert guard._scan_file(target) == []

    def test_noqa_with_em_dash_justification_suppresses(self, tmp_path: Path) -> None:
        target = tmp_path / "ok.py"
        target.write_text(f'TOKEN = "{SK_KEY}"  # noqa: secret — legacy fixture for replay\n')
        assert guard._scan_file(target) == []

    def test_noqa_without_justification_flagged(self, tmp_path: Path) -> None:
        target = tmp_path / "bad.py"
        target.write_text(f'TOKEN = "{SK_KEY}"  # noqa: secret\n')
        violations = guard._scan_file(target)
        assert len(violations) == 1
        assert "missing justification" in violations[0][2]

    def test_noqa_with_short_reason_flagged(self, tmp_path: Path) -> None:
        # reason ≥ 10 chars required; 5-char reason is rejected.
        target = tmp_path / "bad.py"
        target.write_text(f'TOKEN = "{SK_KEY}"  # noqa: secret -- short\n')
        violations = guard._scan_file(target)
        assert len(violations) == 1
        assert "missing justification" in violations[0][2]

    def test_unreadable_file_returns_empty(self, tmp_path: Path) -> None:
        target = tmp_path / "missing.py"
        # File does not exist; scan must not raise.
        assert guard._scan_file(target) == []


@pytest.mark.unit
class TestIsExempt:
    def test_self_path_is_exempt(self) -> None:
        assert guard._is_exempt(Path(guard.__file__)) is True

    def test_top_level_tests_is_exempt(self) -> None:
        path = guard._REPO_ROOT / "tests" / "unit" / "fake.py"
        assert guard._is_exempt(path) is True

    def test_top_level_scripts_is_exempt(self) -> None:
        path = guard._REPO_ROOT / "scripts" / "fake.py"
        assert guard._is_exempt(path) is True

    def test_nested_scripts_not_exempt(self) -> None:
        # src/sdlc/scripts/foo.py must NOT be exempt — exemption is anchored to top level.
        path = guard._REPO_ROOT / "src" / "sdlc" / "scripts" / "foo.py"
        assert guard._is_exempt(path) is False

    def test_path_outside_repo_not_exempt(self, tmp_path: Path) -> None:
        path = tmp_path / "external.py"
        assert guard._is_exempt(path) is False


@pytest.mark.unit
class TestExpandTargets:
    def test_file_argument_passes_through(self, tmp_path: Path) -> None:
        f = tmp_path / "x.py"
        f.write_text("\n")
        result = guard._expand_targets([str(f)])
        assert result == [f]

    def test_directory_argument_recurses(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("\n")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "b.py").write_text("\n")
        (sub / "ignore.txt").write_text("\n")
        result = guard._expand_targets([str(tmp_path)])
        names = sorted(p.name for p in result)
        assert names == ["a.py", "b.py"]

    def test_empty_argv_handled_by_main(self, tmp_path: Path) -> None:
        # Empty list returns empty list; main() applies the default scan.
        assert guard._expand_targets([]) == []


@pytest.mark.unit
class TestMain:
    def test_clean_target_returns_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = tmp_path / "clean.py"
        target.write_text('x = "ok"\n')
        assert guard.main([str(target)]) == 0
        assert capsys.readouterr().out == ""

    def test_secret_target_returns_one(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = tmp_path / "leak.py"
        target.write_text(f'TOKEN = "{SK_KEY}"\n')
        assert guard.main([str(target)]) == 1
        assert "leak.py" in capsys.readouterr().out

    def test_directory_argument_scanned(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text(f'X = "{SK_KEY}"\n')
        (tmp_path / "b.py").write_text("Y = 1\n")
        assert guard.main([str(tmp_path)]) == 1

    def test_exempt_path_skipped(self, capsys: pytest.CaptureFixture[str]) -> None:
        # Pointing main at the script itself must skip (exempt by self-path).
        assert guard.main([guard.__file__]) == 0
        assert capsys.readouterr().out == ""

    def test_no_args_uses_default_scan(self, capsys: pytest.CaptureFixture[str]) -> None:
        # The repo's own src/sdlc/* must be clean — the hook ships green by design.
        assert guard.main([]) == 0
