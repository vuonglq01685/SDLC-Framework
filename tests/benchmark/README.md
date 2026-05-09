# Benchmark Suite (Story 1.15)

Performance regression gates for NFR-PERF-1 (`scan < 2 s on 200 stories / 1000 tasks`).

All corpora are scaffolded at runtime via `tmp_path` (see `conftest.py`); NO committed fixture trees — regen is automatic per test run.

## Running

```bash
uv run pytest -m benchmark --benchmark-only
```

## CI

The `benchmarks` job in `.github/workflows/ci.yml` runs on `ubuntu-latest` python 3.12 only. Strict budget assertions (`< 2.0 s` cold, `< 100 ms` warm) are enforced there. Windows and macOS runs observe but do not gate on the numeric budget.

Failures are hard CI gates, not informational — a perf regression blocks merge.
