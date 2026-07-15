# ContextForge

> Adaptive repository intelligence that compiles the smallest useful evidence package for an autonomous coding task.

[![CI](https://github.com/rustagiaaryan/contextforge/actions/workflows/ci.yml/badge.svg)](https://github.com/rustagiaaryan/contextforge/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

ContextForge is an adaptive repository-intelligence and context-engineering platform that combines hybrid retrieval, code knowledge graphs, Git-history memory, and token-budgeted evidence selection to help autonomous coding agents understand large codebases.

Give it a repository, a software task, and a hard token budget. It returns ranked source ranges, symbols, relationships, tests, and relevant historical changes—with an audit trail for why every item was found, scored, selected, or rejected.

```text
Task: "Requests through mounted applications lose their route prefix."
                              │
                       adaptive route
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
     BM25 + symbols     local embeddings      Git memory
          └──────────────► search anchors ◄──────┘
                              │
                  bounded graph expansion
                    calls · imports · tests
                              │
                       query evolution ×1
                              │
                  explainable weighted ranker
                              │
                  diversity-aware optimizer
                              ▼
              JSON / Markdown evidence package
```

## Why this exists

Coding agents waste context and tool calls exploring plausible but irrelevant files. Embeddings retrieve similar code but miss causal structure. Graph traversal captures structure but can wander. ContextForge starts with strong lexical, symbol, and semantic anchors, expands only a small structural neighborhood, deliberately locates validation code, gates historical memory, then chooses diverse evidence under a strict rendered-token budget.

It is a real local engine—not a chatbot, UI mock, or mandatory cloud wrapper:

- persistent SQLite/FTS5 repository index with content-hash invalidation;
- Python AST extraction for files, modules, classes, functions, methods, tests, signatures, docs, imports, calls, inheritance, and references;
- typed repository/directory/file/module/class/function/method/test/commit graph;
- field-weighted BM25, exact/fuzzy symbols, and deterministic local hash embeddings;
- cached batched embeddings with a provider protocol and graceful semantic fallback;
- bounded anchor-based graph expansion with confidence and distance penalties;
- related-test discovery from calls, imports, references, names, paths, and task overlap;
- confidence-gated Git search, co-changes, hotspots, and rename/move memory;
- deterministic routing, one bounded query-evolution pass, and an explainable reranker;
- submodular-style context selection with source/file/test diversity and redundancy penalties;
- Python API, CLI, eleven typed MCP tools, benchmark harness, and a live local dashboard;
- no API key, model download, graph service, or target-code execution in the default path.

## Quick start

ContextForge requires Python 3.11+ and uses [`uv`](https://docs.astral.sh/uv/) for reproducible environments.

```bash
git clone https://github.com/rustagiaaryan/contextforge.git
cd contextforge
uv sync --extra dev

uv run contextforge index tests/fixtures/sample_repo
uv run contextforge compile tests/fixtures/sample_repo \
  --task "Requests through mounted applications lose their route prefix." \
  --token-budget 1600 --format markdown
```

Launch the Repository Observatory:

```bash
uv run contextforge dashboard tests/fixtures/sample_repo --open
```

The real-output dashboard shows the routing decision, anchors, expanded graph, candidate audit, budget allocation, selected source, tests, Git memory, and stage timings. See the verified [demo walkthrough](docs/DEMO.md).

## Python API

```python
from contextforge import ContextForge

engine = ContextForge.open("./repository")
report = engine.index()

result = engine.compile_context(
    task="Requests through mounted sub-applications lose their route prefix.",
    token_budget=8_000,
)

print(result.to_markdown())
result.to_json()
```

Incremental indexing skips unchanged content and preserves cached embeddings for unchanged units. `compile_context` automatically creates a missing index.

## CLI

```bash
# Incremental source, graph, embedding, and Git index
contextforge index ./repository --json
contextforge status ./repository

# Hybrid ranked search
contextforge search ./repository \
  --task "mounted route prefix regression" --limit 20

# Strict-budget package from an issue file
contextforge compile ./repository \
  --task-file issue.md --token-budget 8000 \
  --format json --output evidence.json

# All required baselines; add --ablations for eight component ablations
contextforge evaluate \
  --dataset benchmarks/sample_tasks.jsonl \
  --token-budget 2000 --top-k 3 --ablations

# Network-opt-in evaluation against pinned real public fixes
contextforge evaluate-history \
  --manifest benchmarks/historical_patches.jsonl \
  --workspace .contextforge/historical-benchmark \
  --token-budget 8000 --top-k 10

# Local visualization and stdio MCP server
contextforge dashboard ./repository --open
contextforge mcp
```

Repository settings can live in `.contextforge.toml` and be overridden with documented environment variables. See [Configuration](docs/CONFIGURATION.md).

## MCP integration

ContextForge exposes `index_repository`, `get_index_status`, `search_symbols`, `search_code`, `get_symbol`, `get_callers`, `get_callees`, `find_related_tests`, `search_git_history`, `expand_graph_neighbors`, and `compile_task_context`.

```json
{
  "mcpServers": {
    "contextforge": {
      "command": "uv",
      "args": ["--directory", "<path-to-contextforge>", "run", "contextforge", "mcp"]
    }
  }
}
```

Every tool takes an explicit local repository path. Full schemas, bounds, and installed-package configuration are in [MCP setup](docs/MCP.md).

## Evidence package

Every selected item preserves source identity and retrieval provenance:

```json
{
  "file": "app/routing.py",
  "symbol": "app.routing.Mount.resolve",
  "start_line": 13,
  "end_line": 15,
  "estimated_tokens": 89,
  "score": 0.745,
  "why_selected": "Selected for relevance and structural coverage.",
  "retrieved_by": ["bm25", "symbol_search", "call_graph"],
  "content_hash": "8bf1…",
  "source_pointer": "contextforge://unit/method:app/routing.py:app.routing.Mount.resolve"
}
```

The package also contains its route, initial anchors, one-pass query evolution, relevant commits, hotspots, complete selected/rejected decisions, semantic availability, and measured stage timings. Markdown output accounts for metadata and source blocks, then removes the lowest-valued evidence until its deterministic estimate is at or below the requested budget.

## Architecture

| Layer | Implementation |
| --- | --- |
| Parsing | Ignore-aware traversal; Python AST and source ranges behind a parser protocol |
| Persistence | Repository-local SQLite, FTS5, WAL, atomic per-file replacement, schema migration |
| Graph | Typed confidence-weighted nodes/edges; cached bounded adjacency queries |
| Retrieval | BM25, fuzzy symbols, local embeddings, graph, tests, Git, hotspots |
| Control | Deterministic router, one-pass query evolution, weighted reranker |
| Selection | Token-aware marginal utility with coverage, connectivity, test, and redundancy signals |
| Interfaces | Python, Typer CLI, FastMCP stdio server, FastAPI dashboard |
| Evaluation | Seven configurations, eight ablations, ranking/coverage/cost/latency/memory metrics |

The graph supplements search rather than replacing it. Dynamic Python relationships remain confidence-weighted best-effort facts, never authoritative static analysis. Read the full [architecture](docs/ARCHITECTURE.md) and [decision records](docs/DECISIONS.md).

## Real historical-patch evaluation

ContextForge was evaluated on 12 pinned, merged bug-fix pull requests: four each from
[Click](https://github.com/pallets/click), [HTTPX](https://github.com/encode/httpx), and
[Typer](https://github.com/fastapi/typer). Each task uses the PR title as the query, checks out
the repository immediately before the fix, and treats the Python files changed by the real
developer patch as gold evidence. The manifest validates every base/fix commit and changed-file
label before evaluation.

At an 8,000-token budget and K=10, the checked
[`historical_patches.json`](benchmarks/results/historical_patches.json) run measured:

| Configuration | Package hit rate | Package file recall | All fix files found | Avg evidence tokens | Token reduction |
| --- | ---: | ---: | ---: | ---: | ---: |
| Filename baseline | 8.3% | 8.3% | 8.3% | 13,596 | 90.6% |
| BM25 only | 58.3% | 42.4% | 33.3% | 5,512 | 97.2% |
| Semantic only | 75.0% | 48.6% | 25.0% | 2,239 | 98.7% |
| Hybrid | 100.0% | 80.6% | 58.3% | 7,954 | 95.6% |
| Hybrid + graph | **100.0%** | **88.9%** | **75.0%** | 7,966 | 95.6% |
| Hybrid + graph + history | 100.0% | 84.7% | 66.7% | 7,978 | 95.6% |
| Full adaptive package | 91.7% | 69.4% | 41.7% | 5,742 | **96.8%** |

The full package retrieved at least one file from the eventual fix in 11 of 12 tasks, selected
18 distinct files / 36 source ranges on average, and reduced the estimated source context from
193,838 to 5,742 tokens. All 12 full packages stayed within the requested budget. Package hit
rate is **not patch success**: this benchmark measures whether useful evidence was retrieved,
not whether an agent or developer completed the fix. It is curated and small; the 95% Wilson
interval for the 11/12 hit rate is 64.6%–98.5%. See [Evaluation](docs/EVALUATION.md) for the
selection policy, exact definitions, limitations, and reproduction command.

## Preliminary fixture evaluation

These are actual results from [`benchmarks/results/preliminary.json`](benchmarks/results/preliminary.json), produced on 2026-07-14 with Python 3.11.12 on macOS arm64:

```bash
uv run contextforge evaluate \
  --dataset benchmarks/sample_tasks.jsonl \
  --token-budget 2000 --top-k 3 --ablations
```

The dataset is only three deterministic tasks over a four-file Python fixture. It validates the harness and demonstrates a signal over a filename baseline; it is **not** evidence of broad real-world generalization.

| Configuration | File Recall@3 | File Precision@3 | MRR | NDCG@3 | Avg context tokens | Retrieval ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Filename baseline | 0.778 | 0.556 | 0.500 | 0.564 | 245 | 1.42 |
| BM25 only | 0.889 | 0.667 | 1.000 | 0.922 | 294 | 10.01 |
| Semantic only | 0.778 | 0.556 | 1.000 | 0.823 | 285 | 9.05 |
| Hybrid | 0.889 | 0.667 | 1.000 | 0.922 | 619 | 27.88 |
| Hybrid + graph | 0.889 | 0.667 | 1.000 | 0.922 | 655 | 77.33 |
| Hybrid + graph + history | 0.889 | 0.667 | 1.000 | 0.922 | 655 | 85.65 |
| Full adaptive pipeline | **0.889** | **0.667** | **1.000** | **0.922** | 885 | 103.21 |

At K=3, the full pipeline improves file recall by 0.111, MRR by 0.500, and NDCG by
0.358 over the filename baseline. The package costs more than sending this four-file fixture
because explanations and provenance dominate its 198 raw-source-token baseline. This tiny
corpus validates machinery; it is not a compression benchmark.

Selected ablation findings:

| Variant | File Recall@3 | NDCG@3 | Avg tokens | Retrieval ms |
| --- | ---: | ---: | ---: | ---: |
| Full | 0.889 | 0.922 | 885 | 103.21 |
| Without graph | 0.889 | 0.922 | 738 | 46.65 |
| Without token optimization | 0.889 | 0.922 | 1,144 | 78.01 |
| Without redundancy penalty | 0.778 | 0.844 | 1,144 | 82.10 |

The full pipeline's gold-line coverage (0.415) is lower than the filename baseline (0.688) because it prefers compact symbol ranges over whole files. Both metrics are retained because token-efficient evidence and raw line coverage measure different tradeoffs. See [Evaluation](docs/EVALUATION.md) for metric definitions and limitations.

## Measured local performance

[`self_performance.json`](benchmarks/results/self_performance.json) records one no-warmup run on this repository at 72 Python files, 429 source units, 452 graph nodes, 2,086 edges, and 15 commits.

| Operation | Measured latency |
| --- | ---: |
| Clean index, including 357 local embeddings | 1.931 s |
| Incremental index, 0 files re-parsed / 0 embeddings regenerated | 437 ms |
| Hybrid search, 20 results | 33 ms |
| Full 8,000-token compilation, 86 candidates / 23 selected | 1.138 s |

The benchmark process peaked at 54.1 MB RSS. These are single-machine preliminary measurements, not service-level guarantees.

## Docker

```bash
docker build -t contextforge .
docker run --rm -v "$PWD:/workspace" contextforge index /workspace
```

The image contains the keyless local baseline. Mount target repositories read/write if their `.contextforge/` index should persist.

## Security and privacy

Repository text, paths, issue descriptions, and Git metadata are untrusted. ContextForge parses source but never imports or executes it. SQLite statements are parameterized, Git indexing uses bounded read commands without a shell, traversal rejects symlinks and escapes, MCP graph operations are capped, and the dashboard binds to loopback by default.

Retrieved comments can still contain prompt injection; downstream agents must treat evidence as data. Do not expose the dashboard or MCP process directly to an untrusted network. See [Security](docs/SECURITY.md) and report vulnerabilities privately through GitHub.

## Limitations

- Python is the only first-class parser. Interfaces are ready for additional languages, but no Tree-sitter adapters ship yet.
- Call/reference resolution is best-effort for dynamic Python; there is no control-flow or data-flow slice in v0.1.
- The default embedding provider is deterministic feature hashing, not a trained semantic model.
- The real benchmark is a curated 12-task retrieval proxy, not an untouched or representative
  holdout. There is no downstream patch-success or developer-productivity evaluation yet.
- The reranker is an explainable weighted model, not learned-to-rank; top-10 recall trails its
  complete-package recall and hybrid + graph outperforms the full adaptive route on this suite.
- History gating favors precision and can omit relevant patches whose messages and diffs use unrelated terminology.

## Roadmap

1. Tree-sitter language adapters and Python definition-use/data-flow slicing.
2. Opt-in trained local embeddings, cross-encoder reranking, and a larger untouched holdout suite.
3. Native ContextBench subset adapter and larger multi-repository evaluation.
4. Incremental graph/history rebuilding and approximate nearest-neighbor search.
5. Downstream agent task-success experiments on issue-resolution benchmarks.

## Research inspirations

ContextForge is informed by [RepoCoder's iterative repository retrieval](https://arxiv.org/abs/2303.12570), [ContextBench's process-oriented context metrics](https://arxiv.org/abs/2602.05892), [SWE-bench's repository issue formulation](https://arxiv.org/abs/2310.06770), [CodeSearchNet's semantic code-search evaluation](https://arxiv.org/abs/1909.09436), [CodeRAG's anchor-to-graph framing](https://arxiv.org/abs/2504.10046), and [maximal marginal relevance](https://www.cs.cmu.edu/~jgc/publication/The_Use_MMR_Diversity_Based_LTMIR_1998.pdf). These links describe external work; the results above are ContextForge's own checked-in measurements.

## Development

```bash
uv sync --extra dev
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest --cov=contextforge --cov-report=term-missing
```

See [Contributing](CONTRIBUTING.md), the living [plan](docs/PLAN.md), and [release notes](docs/RELEASE_NOTES.md).

## License

[MIT](LICENSE) © 2026 Aaryan Rustagi
