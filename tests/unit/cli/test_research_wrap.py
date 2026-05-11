"""Unit tests for ``_wrap_research_artifact`` (Story 2A.9, AC6)."""

from __future__ import annotations

import pytest
import yaml

from sdlc.cli.research import _wrap_research_artifact

pytestmark = pytest.mark.unit


def test_byte_stable_same_inputs() -> None:
    a = _wrap_research_artifact("body\n", topic="t", slug="my-slug", ts="2020-01-01T00:00:00.000Z")
    b = _wrap_research_artifact("body\n", topic="t", slug="my-slug", ts="2020-01-01T00:00:00.000Z")
    assert a == b


def test_byte_stable_golden() -> None:
    """P7 (code review): pin the exact byte output, not just determinism.

    Asserting two calls with identical inputs return ``a == b`` only proves
    determinism (any pure function passes that); it does NOT prove byte-stability
    across YAML library versions, locale, or future helper edits. Pin the bytes.
    """
    out = _wrap_research_artifact(
        "## Research Findings\n\nBody.\n",
        topic="PCI compliance scope",
        slug="pci-compliance-scope",
        ts="2020-01-01T00:00:00.000Z",
    )
    expected = (
        "---\n"
        "kind: research\n"
        "researched_at: '2020-01-01T00:00:00.000Z'\n"
        "researched_by_specialist: technical-researcher\n"
        "schema_version: 1\n"
        "slug: pci-compliance-scope\n"
        "topic: PCI compliance scope\n"
        "---\n"
        "\n"
        "# Pci Compliance Scope\n"
        "\n"
        "## Research Findings\n"
        "\n"
        "Body.\n"
    )
    assert out == expected


def test_yaml_special_topic_round_trip() -> None:
    topic = "a'b\"c:\nline"
    wrapped = _wrap_research_artifact(
        "## H\n\nx\n", topic=topic, slug="ab", ts="2020-01-01T00:00:00.000Z"
    )
    segments = wrapped.split("---", 2)
    front = yaml.safe_load(segments[1])
    assert isinstance(front, dict)
    assert front["topic"] == topic


def test_trailing_newline_present() -> None:
    w = _wrap_research_artifact("x", topic="t", slug="ab-cd", ts="2020-01-01T00:00:00.000Z")
    assert w.endswith("\n")
