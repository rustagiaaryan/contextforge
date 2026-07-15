# Benchmarks

## Deterministic fixture

`sample_tasks.jsonl` contains three tasks over the checked-in four-file repository. It exercises a
cross-file bug, symbol/call retrieval, and implementation-plus-test discovery. It is deliberately
small enough for CI and validates the evaluation machinery; it is not broad evidence.

```bash
uv run contextforge evaluate --dataset benchmarks/sample_tasks.jsonl \
  --token-budget 2000 --top-k 3 --ablations
```

## Historical public fixes

`historical_patches.jsonl` pins 12 public merged bug-fix PRs from Click, HTTPX, and Typer. The
network-opt-in runner clones each repository, verifies the base/fix ancestry and exact changed
Python files, checks out the pre-fix state, and evaluates the real PR title against the files the
developer later changed.

```bash
uv run contextforge evaluate-history \
  --manifest benchmarks/historical_patches.jsonl \
  --workspace .contextforge/historical-benchmark \
  --token-budget 8000 --top-k 10 \
  --output benchmarks/results/historical_patches.json
```

The checked run used about 400 MB of temporary clone/snapshot space. The workspace is ignored and
can be deleted after the run. ContextForge parses text and Git metadata; it never imports or
executes downloaded repository code.

The result includes both top-K ranking and full-package metrics. A package hit means at least one
file from the eventual developer patch appeared somewhere in the compiled evidence. It does not
mean an agent successfully implemented or tested the fix. See `docs/EVALUATION.md` for exact
results, statistical limits, and claim wording.
