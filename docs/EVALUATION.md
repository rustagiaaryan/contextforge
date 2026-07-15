# Evaluation

Evaluation is a product feature: every retrieval component should justify the context it consumes.

## Dataset format

Each JSONL task identifies a repository, natural-language task, gold files, optional gold symbols
and line ranges, and metadata. Fixture repositories keep CI deterministic; external downloads are
always opt-in.

## Compared configurations

The harness evaluates filename baseline, BM25, semantic-only, hybrid, hybrid plus graph, hybrid
plus graph/history, and the full adaptive pipeline. Ablations individually disable semantics,
graph expansion, history, test discovery, query evolution, routing, token optimization, and
redundancy penalties.

## Metrics

- File and symbol Precision/Recall@K, Hit@K, complete recall, MRR, and NDCG
- Package-level file recall, precision, hit rate, and complete recall over every selected range
- Gold-line coverage and selected-context relevance
- Complete-package context tokens, whole-repository source tokens, tokens saved, and reduction
- Index/retrieval latency, peak memory, graph expansion count, and evidence-source diversity

Ranking metrics use only the first K selected items. Package metrics use every item delivered
under the requested budget. `repository_source_tokens` is the sum of all indexed Python file
contents using ContextForge's deterministic `ceil(characters / 4)` estimator.
`token_reduction_fraction` compares complete evidence blocks—including source and provenance
headers—with that raw-source baseline. It is an estimate, not a provider-specific tokenizer.

## Claim policy

Checked summaries contain the command, environment, timestamp, dataset hash, configuration, and
raw aggregate values. Results are labelled **measured**, **preliminary**, or **external**. Missing
experiments are never inferred or fabricated.

## Measured historical-patch benchmark

[`historical_patches.jsonl`](../benchmarks/historical_patches.jsonl) pins 12 merged bug-fix PRs,
four each from Click, HTTPX, and Typer. The selection policy was fixed before retrieval ran:
descriptive bug-fix titles, one to four changed Python files, and no documentation-only or
dependency-only patches. The runner:

1. downloads an ordinary public GitHub HTTPS repository without executing its code;
2. validates that the pinned base is an ancestor of the pinned fix;
3. verifies that manifest gold files exactly match the real patch;
4. checks out an isolated snapshot at the pre-fix base commit; and
5. runs all seven retrieval configurations against the PR title.

The checked
[`historical_patches.json`](../benchmarks/results/historical_patches.json) run used an 8,000-token
budget, K=10, Python 3.11.12, and macOS arm64. Across 12 versioned snapshots, the harness indexed
3,029 Python files, 26,979 source units, and 2,326,055 estimated source tokens. The average
snapshot contained 193,838 source tokens; all 12 exceeded the context budget.

| Configuration | Package hit | Package file recall | Package complete recall | P@10 | R@10 | Avg package tokens | Token reduction |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Filename baseline | 8.3% | 8.3% | 8.3% | 0.8% | 8.3% | 13,596 | 90.6% |
| BM25 only | 58.3% | 42.4% | 33.3% | 7.5% | 42.4% | 5,512 | 97.2% |
| Semantic only | 75.0% | 48.6% | 25.0% | 9.2% | 48.6% | 2,239 | 98.7% |
| Hybrid | 100.0% | 80.6% | 58.3% | 5.0% | 29.2% | 7,954 | 95.6% |
| Hybrid + graph | **100.0%** | **88.9%** | **75.0%** | 5.0% | 29.2% | 7,966 | 95.6% |
| Hybrid + graph + history | 100.0% | 84.7% | 66.7% | 5.0% | 29.2% | 7,978 | 95.6% |
| Full adaptive | 91.7% | 69.4% | 41.7% | 7.5% | 39.6% | 5,742 | **96.8%** |

The full adaptive package found at least one eventual fix file in 11 of 12 tasks, found 69.4%
of all changed Python files on average, and selected 18 distinct files / 36 symbol ranges on
average. It reduced estimated context by 188,096 tokens per task. Every full package obeyed the
8,000-token limit. Package precision was 11.3%, reflecting that packages include architectural
neighbors and tests beyond the small one-to-four-file gold patch.

The full adaptive route trails hybrid + graph on package recall because it reserves budget for
routing, query evolution, Git evidence, timings, and selection explanations, and may gate
sources. This measured negative result is a target for future ranking work.

### Statistical and causal limits

- The 91.7% package hit rate is 11/12; its 95% Wilson interval is 64.6%–98.5%.
- Tasks are curated, not random, and PR titles sometimes name an affected API.
- This suite hardened overload parsing and broad-commit co-change handling; it is not an untouched
  holdout set.
- Changed files are a retrieval proxy. They do not prove the selected lines are sufficient, an
  agent will write a correct patch, or developers finish faster.
- Snapshots repeat projects at different commits, so 2.33M tokens is workload volume rather than
  unique code volume.

Resume-safe wording is: **“On a curated 12-task historical-patch benchmark, ContextForge's full
packages retrieved at least one eventual fix file in 11/12 tasks while reducing estimated source
context by 96.8% on average.”** Do not call this 91.7% patch accuracy or a 96.8% reduction in
developer time.

## Preliminary fixture results

The checked [`preliminary.json`](../benchmarks/results/preliminary.json) run uses three tasks over
a four-file fixture, a 2,000-token budget, K=3, Python 3.11.12, and macOS arm64. It validates the
harness rather than broad retrieval quality.

| Configuration | File R@3 | File P@3 | Symbol R@3 | MRR | NDCG@3 | Gold-line coverage | Package tokens | Latency ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Filename baseline | 0.778 | 0.556 | 0.000 | 0.500 | 0.564 | 0.688 | 245 | 1.42 |
| BM25 only | 0.889 | 0.667 | 0.778 | 1.000 | 0.922 | 0.658 | 294 | 10.01 |
| Semantic only | 0.778 | 0.556 | 0.667 | 1.000 | 0.823 | 0.716 | 285 | 9.05 |
| Hybrid | 0.889 | 0.667 | 0.778 | 1.000 | 0.922 | 0.658 | 619 | 27.88 |
| Hybrid + graph | 0.889 | 0.667 | 0.778 | 1.000 | 0.922 | 0.658 | 655 | 77.33 |
| Hybrid + graph + history | 0.889 | 0.667 | 0.778 | 1.000 | 0.922 | 0.658 | 655 | 85.65 |
| Full adaptive | 0.889 | 0.667 | 0.611 | 1.000 | 0.922 | 0.415 | 885 | 103.21 |

All eight ablations ran. Removing the redundancy penalty reduced file Recall@3 from 0.889 to
0.778 and NDCG@3 from 0.922 to 0.844 while increasing package evidence from 885 to 1,144 tokens.
Removing token optimization also increased evidence to 1,144 tokens. Removing graph expansion
kept top-three quality and reduced latency to 46.65 ms.

The clean fixture index took 160.74 ms with 0.229 MB Python-traced peak memory. An immediate
incremental index took 53.63 ms and parsed zero files. Because the fixture contains only 198 raw
source tokens, explanation overhead creates negative token savings; compression claims therefore
use the historical benchmark.

## Reproduction

Run the deterministic fixture and all ablations:

```bash
rm -rf tests/fixtures/sample_repo/.contextforge
uv run contextforge evaluate \
  --dataset benchmarks/sample_tasks.jsonl \
  --token-budget 2000 --top-k 3 --ablations
```

The historical run is network opt-in and uses pinned public GitHub data:

```bash
uv run contextforge evaluate-history \
  --manifest benchmarks/historical_patches.jsonl \
  --workspace .contextforge/historical-benchmark \
  --token-budget 8000 --top-k 10 \
  --output benchmarks/results/historical_patches.json
```

The workspace caches full Git clones and pre-fix snapshots and used roughly 400 MB for the
checked run. It is ignored by Git and can be removed afterward. Memory tracing is disabled for
this suite because Python `tracemalloc` materially distorted latency; the result records
`memory_tracing_enabled: false` and zero traced peak memory rather than inventing a measurement.
