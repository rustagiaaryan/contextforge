# Included benchmark

`sample_tasks.jsonl` contains three deterministic tasks over the checked-in fixture repository. It exercises a cross-file bug, symbol/call retrieval, and implementation-plus-test discovery. It is deliberately small enough for CI and validates the evaluation machinery; it is not evidence of broad real-world generalization.

Run every required configuration:

```bash
uv run contextforge evaluate --dataset benchmarks/sample_tasks.jsonl \
  --token-budget 2000 --top-k 10
```

Add all eight component ablations with `--ablations`. External datasets are opt-in: convert a manageable ContextBench subset into the documented JSONL schema, keep repository paths relative to the dataset, and pass that local file through `--dataset`. ContextForge never downloads external repositories or datasets implicitly.

