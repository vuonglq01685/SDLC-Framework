"""Performance benchmark for engine.scanner.scan — NFR-PERF-1 CI gate (Story 1.15).

Budget: cold < 2.0 s, warm < 100 ms on ubuntu-latest python 3.12.
Corpus: 4 epics x 50 stories x 5 tasks = 200 stories + 1000 tasks (built at runtime).
Skipped on Windows: NFR-PERF-1 gate runs on Linux CI per AC4 (Defender +
filesystem behaviour make the budget noisy on win32).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pytest_benchmark.fixture import BenchmarkFixture

from benchmark.conftest import _build_perf_corpus
from sdlc.engine.scanner import scan

pytestmark = [
    pytest.mark.benchmark,
    pytest.mark.skipif(
        sys.platform == "win32",
        reason="NFR-PERF-1 gate runs on Linux CI per AC4",
    ),
]


def test_scan_perf_cold(benchmark: BenchmarkFixture, tmp_path: Path) -> None:
    corpus = tmp_path / "perf_corpus"
    corpus.mkdir()
    _build_perf_corpus(corpus)
    # One true cold sample per CI run: rounds=1, iterations=1, no warmup.
    # Variance is high but the 10x headroom over median (~200ms vs 2s gate)
    # absorbs it; multi-round averaging would mask cold-start regressions.
    benchmark.pedantic(  # type: ignore[no-untyped-call]
        scan, args=(corpus,), iterations=1, rounds=1, warmup_rounds=0
    )
    mean = benchmark.stats.stats.mean  # type: ignore[union-attr]
    assert mean < 2.0, (
        f"scan() cold ran in {mean:.3f}s on 200/1000 corpus; budget is 2.0s (NFR-PERF-1)"
    )


def test_scan_perf_warm(benchmark: BenchmarkFixture, tmp_path: Path) -> None:
    corpus = tmp_path / "perf_corpus"
    corpus.mkdir()
    _build_perf_corpus(corpus)
    # Warm the OS file cache with one pre-benchmark call.
    scan(corpus)
    benchmark.pedantic(  # type: ignore[no-untyped-call]
        scan, args=(corpus,), iterations=10, rounds=5, warmup_rounds=2
    )
    mean = benchmark.stats.stats.mean  # type: ignore[union-attr]
    assert mean < 0.1, (
        f"scan() warm ran in {mean:.3f}s on 200/1000 corpus; budget is 100ms (NFR-PERF-1)"
    )
