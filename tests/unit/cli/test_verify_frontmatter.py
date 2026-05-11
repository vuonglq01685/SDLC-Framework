"""Unit tests for `cli/verify` frontmatter helpers + `_Verification` model (Story 2A.10, Task 1).

Covers AC5 (frontmatter append semantics) + AC6 (`_Verification` schema). Tests the four
pure helpers `_Verification`, `_parse_frontmatter`, `_append_verification`, `_serialize_artifact`
authored in `src/sdlc/cli/verify.py` per AC8/D1 (single-file layout).
"""

from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

pytestmark = pytest.mark.unit


_VALID_TS = "2026-05-11T12:34:56.789Z"
_VALID_HASH = "sha256:" + "a" * 64


# ---------------------------------------------------------------------------
# _Verification model (AC6)
# ---------------------------------------------------------------------------


class TestVerificationModel:
    def test_happy_path_minimum_fields(self) -> None:
        from sdlc.cli.verify import _Verification

        entry = _Verification(
            verifier="artifact-verifier",
            ts=_VALID_TS,
            content_hash_at_verify=_VALID_HASH,
        )
        assert entry.schema_version == 1
        assert entry.verifier == "artifact-verifier"
        assert entry.ts == _VALID_TS
        assert entry.status == "verified"
        assert entry.content_hash_at_verify == _VALID_HASH
        assert entry.verifier_note is None

    def test_status_default_is_verified(self) -> None:
        from sdlc.cli.verify import _Verification

        entry = _Verification(
            verifier="artifact-verifier",
            ts=_VALID_TS,
            content_hash_at_verify=_VALID_HASH,
        )
        assert entry.status == "verified"

    def test_accepts_failed_and_advisory_status(self) -> None:
        from sdlc.cli.verify import _Verification

        for status in ("verified", "failed", "advisory"):
            entry = _Verification(
                verifier="artifact-verifier",
                ts=_VALID_TS,
                status=status,
                content_hash_at_verify=_VALID_HASH,
            )
            assert entry.status == status

    def test_rejects_invalid_status(self) -> None:
        from sdlc.cli.verify import _Verification

        with pytest.raises(ValidationError):
            _Verification(
                verifier="artifact-verifier",
                ts=_VALID_TS,
                status="approved",  # not in literal set
                content_hash_at_verify=_VALID_HASH,
            )

    def test_rejects_invalid_ts_pattern(self) -> None:
        from sdlc.cli.verify import _Verification

        with pytest.raises(ValidationError):
            _Verification(
                verifier="artifact-verifier",
                ts="2026-05-11 12:34:56",  # wrong shape — missing T and Z
                content_hash_at_verify=_VALID_HASH,
            )

        with pytest.raises(ValidationError):
            _Verification(
                verifier="artifact-verifier",
                ts="not-a-timestamp",
                content_hash_at_verify=_VALID_HASH,
            )

    def test_rejects_invalid_content_hash(self) -> None:
        from sdlc.cli.verify import _Verification

        for bad_hash in (
            "sha256:short",
            "sha512:" + "a" * 128,
            "a" * 64,
            "sha256:" + "Z" * 64,  # uppercase not lowercase hex
        ):
            with pytest.raises(ValidationError):
                _Verification(
                    verifier="artifact-verifier",
                    ts=_VALID_TS,
                    content_hash_at_verify=bad_hash,
                )

    def test_rejects_extra_fields(self) -> None:
        from sdlc.cli.verify import _Verification

        with pytest.raises(ValidationError):
            _Verification(
                verifier="artifact-verifier",
                ts=_VALID_TS,
                content_hash_at_verify=_VALID_HASH,
                unknown_field="oops",  # type: ignore[call-arg]
            )

    def test_verifier_note_max_500(self) -> None:
        from sdlc.cli.verify import _Verification

        entry = _Verification(
            verifier="artifact-verifier",
            ts=_VALID_TS,
            content_hash_at_verify=_VALID_HASH,
            verifier_note="x" * 500,
        )
        assert entry.verifier_note is not None
        assert len(entry.verifier_note) == 500

        with pytest.raises(ValidationError):
            _Verification(
                verifier="artifact-verifier",
                ts=_VALID_TS,
                content_hash_at_verify=_VALID_HASH,
                verifier_note="x" * 501,
            )

    def test_is_immutable(self) -> None:
        from sdlc.cli.verify import _Verification

        entry = _Verification(
            verifier="artifact-verifier",
            ts=_VALID_TS,
            content_hash_at_verify=_VALID_HASH,
        )
        with pytest.raises(ValidationError):
            entry.verifier = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# _parse_frontmatter (AC5)
# ---------------------------------------------------------------------------


class TestParseFrontmatter:
    def test_no_frontmatter_returns_empty_dict_and_full_body(self) -> None:
        from sdlc.cli.verify import _parse_frontmatter

        body = "# Heading\n\nSome content.\n"
        fm, rest = _parse_frontmatter(body)
        assert fm == {}
        assert rest == body

    def test_basic_frontmatter_parses(self) -> None:
        from sdlc.cli.verify import _parse_frontmatter

        content = "---\ntitle: Hello\nphase: 1\n---\n# Body\n"
        fm, body = _parse_frontmatter(content)
        assert fm == {"title": "Hello", "phase": 1}
        assert body == "# Body\n"

    def test_empty_frontmatter_block(self) -> None:
        from sdlc.cli.verify import _parse_frontmatter

        content = "---\n---\n# Body\n"
        fm, body = _parse_frontmatter(content)
        assert fm == {}
        assert body == "# Body\n"

    def test_frontmatter_with_list_value(self) -> None:
        from sdlc.cli.verify import _parse_frontmatter

        content = (
            "---\n"
            "verifications:\n"
            "  - verifier: artifact-verifier\n"
            "    ts: 2026-05-11T12:00:00Z\n"
            "---\n"
            "# Body\n"
        )
        fm, _body = _parse_frontmatter(content)
        assert isinstance(fm.get("verifications"), list)
        assert len(fm["verifications"]) == 1
        assert fm["verifications"][0]["verifier"] == "artifact-verifier"

    def test_invalid_yaml_raises_workflow_error(self) -> None:
        from sdlc.cli.verify import _parse_frontmatter
        from sdlc.errors import WorkflowError

        bad = "---\ntitle: : : :\n---\n# Body\n"
        with pytest.raises(WorkflowError):
            _parse_frontmatter(bad)

    def test_non_mapping_frontmatter_raises_workflow_error(self) -> None:
        from sdlc.cli.verify import _parse_frontmatter
        from sdlc.errors import WorkflowError

        content = "---\n- item1\n- item2\n---\n# Body\n"
        with pytest.raises(WorkflowError):
            _parse_frontmatter(content)


# ---------------------------------------------------------------------------
# _append_verification (AC5)
# ---------------------------------------------------------------------------


class TestAppendVerification:
    def _entry(self, ts: str = _VALID_TS, hash_: str = _VALID_HASH):
        from sdlc.cli.verify import _Verification

        return _Verification(
            verifier="artifact-verifier",
            ts=ts,
            content_hash_at_verify=hash_,
        )

    def test_appends_to_empty_frontmatter(self) -> None:
        from sdlc.cli.verify import _append_verification

        entry = self._entry()
        result = _append_verification({}, entry)
        assert "verifications" in result
        assert len(result["verifications"]) == 1
        assert result["verifications"][0]["verifier"] == "artifact-verifier"

    def test_initializes_verifications_when_absent(self) -> None:
        from sdlc.cli.verify import _append_verification

        fm = {"title": "PRODUCT"}
        entry = self._entry()
        result = _append_verification(fm, entry)
        assert result.get("title") == "PRODUCT"
        assert result["verifications"] == [
            {
                "schema_version": 1,
                "verifier": "artifact-verifier",
                "ts": _VALID_TS,
                "status": "verified",
                "content_hash_at_verify": _VALID_HASH,
                "verifier_note": None,
            }
        ]

    def test_initializes_when_verifications_is_none(self) -> None:
        from sdlc.cli.verify import _append_verification

        fm = {"verifications": None}
        result = _append_verification(fm, self._entry())
        assert isinstance(result["verifications"], list)
        assert len(result["verifications"]) == 1

    def test_appends_without_replacing_existing(self) -> None:
        from sdlc.cli.verify import _append_verification

        existing = {
            "schema_version": 1,
            "verifier": "artifact-verifier",
            "ts": "2026-04-01T00:00:00Z",
            "status": "verified",
            "content_hash_at_verify": "sha256:" + "b" * 64,
            "verifier_note": None,
        }
        fm = {"verifications": [existing]}
        result = _append_verification(fm, self._entry())
        assert len(result["verifications"]) == 2
        assert result["verifications"][0] == existing
        assert result["verifications"][1]["ts"] == _VALID_TS

    def test_does_not_mutate_input(self) -> None:
        from sdlc.cli.verify import _append_verification

        fm = {
            "title": "PRODUCT",
            "verifications": [{"verifier": "x", "ts": "2026-01-01T00:00:00Z"}],
        }
        snapshot = copy.deepcopy(fm)
        _ = _append_verification(fm, self._entry())
        assert fm == snapshot

    def test_round_trip_yaml_safe_dump_byte_stable(self) -> None:
        import yaml

        from sdlc.cli.verify import _append_verification

        fm: dict = {}
        result = _append_verification(fm, self._entry())
        dumped = yaml.safe_dump(
            result, sort_keys=True, default_flow_style=False, allow_unicode=True
        )
        reloaded = yaml.safe_load(dumped)
        assert reloaded == result


# ---------------------------------------------------------------------------
# _serialize_artifact (AC5)
# ---------------------------------------------------------------------------


class TestSerializeArtifact:
    def test_empty_frontmatter_omits_delimiters(self) -> None:
        from sdlc.cli.verify import _serialize_artifact

        body = "# Body\n"
        out = _serialize_artifact({}, body)
        assert out == body
        assert not out.startswith("---")

    def test_round_trip_with_parse_frontmatter(self) -> None:
        from sdlc.cli.verify import _parse_frontmatter, _serialize_artifact

        fm = {"title": "PRODUCT", "phase": 1}
        body = "# Body content\nLine 2\n"
        serialized = _serialize_artifact(fm, body)
        parsed_fm, parsed_body = _parse_frontmatter(serialized)
        assert parsed_fm == fm
        assert parsed_body == body

    def test_trailing_newline_present(self) -> None:
        from sdlc.cli.verify import _serialize_artifact

        out = _serialize_artifact({"a": 1}, "body")
        assert out.endswith("\n")

    def test_keys_sorted_no_flow_style(self) -> None:
        from sdlc.cli.verify import _serialize_artifact

        fm = {"zeta": 1, "alpha": 2, "mu": 3}
        out = _serialize_artifact(fm, "body\n")
        head = out.split("---\n", 2)[1]
        idx_alpha = head.index("alpha")
        idx_mu = head.index("mu")
        idx_zeta = head.index("zeta")
        assert idx_alpha < idx_mu < idx_zeta
        assert "{" not in head
        assert "[" not in head or "verifications" in head

    def test_unicode_preserved(self) -> None:
        from sdlc.cli.verify import _parse_frontmatter, _serialize_artifact

        fm = {"title": "Hồ Sơ Sản Phẩm"}
        body = "# Tiếng Việt\n"
        out = _serialize_artifact(fm, body)
        parsed_fm, parsed_body = _parse_frontmatter(out)
        assert parsed_fm == fm
        assert parsed_body == body

    def test_round_trip_with_appended_verifications(self) -> None:
        from sdlc.cli.verify import (
            _append_verification,
            _parse_frontmatter,
            _serialize_artifact,
            _Verification,
        )

        fm0 = {"title": "PRODUCT"}
        body = "# Body\n"
        entry = _Verification(
            verifier="artifact-verifier",
            ts=_VALID_TS,
            content_hash_at_verify=_VALID_HASH,
        )
        fm1 = _append_verification(fm0, entry)
        serialized = _serialize_artifact(fm1, body)
        parsed_fm, parsed_body = _parse_frontmatter(serialized)
        assert parsed_fm == fm1
        assert parsed_body == body
