# Evaluation

Evaluation is a product feature: every retrieval component should justify the context it consumes.

## Dataset format

Each JSONL task identifies a repository, natural-language task, gold files, optional gold symbols and line ranges, and metadata. Fixture repositories keep CI deterministic; external benchmark downloads are opt-in.

## Compared configurations

The harness will evaluate filename/random baseline, BM25, semantic-only, hybrid, hybrid plus graph, hybrid plus graph/history, and the full adaptive pipeline. Ablations will individually disable semantics, graph expansion, history, test discovery, query evolution, routing, token optimization, and redundancy penalties.

## Metrics

- File and symbol Precision/Recall@K, MRR, and NDCG
- Gold-line coverage and selected-context relevance
- Context token count and tokens per relevant file
- Index/retrieval latency, peak memory, and graph expansion count
- Evidence-source diversity

## Claim policy

Checked-in summaries must contain the command, environment, timestamp, dataset hash, configuration, and raw aggregate values. Results are labelled **measured**, **preliminary**, or **external**. Missing experiments remain goals; they are never inferred or fabricated.

## Preliminary measured results

The checked-in run in `benchmarks/results/preliminary.json` used the three-task/four-file fixture, a 2,000-token budget, K=3, Python 3.11.12, and macOS arm64. It is a harness validation and microbenchmark, not a broad model-quality claim.

| Configuration | File R@3 | File P@3 | Symbol R@3 | MRR | NDCG@3 | Gold-line coverage | Tokens | Latency ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Filename baseline | 0.778 | 0.556 | 0.000 | 0.500 | 0.564 | 0.688 | 245 | 1.41 |
| BM25 only | 0.889 | 0.667 | 0.778 | 1.000 | 0.922 | 0.658 | 294 | 10.18 |
| Semantic only | 0.778 | 0.556 | 0.667 | 1.000 | 0.823 | 0.716 | 285 | 8.99 |
| Hybrid | 0.889 | 0.667 | 0.778 | 1.000 | 0.922 | 0.658 | 263 | 27.49 |
| Hybrid + graph | 0.889 | 0.667 | 0.778 | 1.000 | 0.922 | 0.658 | 275 | 81.45 |
| Hybrid + graph + history | 0.889 | 0.667 | 0.778 | 1.000 | 0.922 | 0.658 | 275 | 94.32 |
| Full adaptive | 0.889 | 0.667 | 0.778 | 1.000 | 0.922 | 0.415 | 261 | 105.00 |

All eight ablations ran. Removing the redundancy penalty reduced file Recall@3 from 0.889 to 0.778 and NDCG@3 from 0.922 to 0.844 while increasing average selected tokens from 261 to 314. Removing token optimization kept the top-three retrieval metrics but increased tokens to 340. Removing graph expansion kept the fixture's top-three retrieval quality and reduced measured latency to 47.02 ms, showing that this small benchmark is too easy to establish a graph benefit.

The same run measured a clean fixture index at 151.32 ms and 0.235 MB Python-traced peak memory. An immediate incremental index took 52.70 ms, parsed zero files, and generated zero embeddings.

## Reproduction and external data

```bash
rm -rf tests/fixtures/sample_repo/.contextforge
uv run contextforge evaluate \
  --dataset benchmarks/sample_tasks.jsonl \
  --token-budget 2000 --top-k 3 --ablations
```

The generic JSONL format accepts repositories checked out beside a dataset, so a manageable ContextBench subset can be converted and evaluated without ContextForge downloading data or requiring provider keys. External benchmark download/checkout remains explicitly opt-in.
