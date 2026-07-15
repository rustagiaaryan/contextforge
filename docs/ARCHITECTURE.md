# ContextForge Architecture

## Objective

ContextForge compiles task-specific repository evidence under a strict token budget and can also
export a portable multi-language repository graph. It is library-first; CLI, MCP, dashboard, graph
artifacts, and the agent skill are adapters over explicit pipelines.

## Components

1. **Traversal and parsing** discover allowed repository files and extract Python modules, classes, functions, methods, tests, signatures, docstrings, imports, calls, and references.
2. **SQLite storage** persists content-addressed source units, an FTS lexical index, typed graph nodes and edges, cached embeddings, Git commits, and co-change counts.
3. **Adaptive routing** classifies tasks with transparent deterministic rules and activates only useful retrieval sources.
4. **Anchor retrieval** combines BM25/FTS, fuzzy and exact symbol matching, and optional semantic similarity.
5. **Structural retrieval** expands a bounded, distance-penalized neighborhood from strong anchors and deliberately discovers validation code.
6. **History memory** gates historical evidence using query overlap, recency, current-file existence, and anchor overlap.
7. **Reranking and evolution** normalize candidates, run one bounded concept-expansion pass, and combine explainable signals without claiming a learned ranker.
8. **Budget optimization** uses relevance, source diversity, structural coverage, test representation, cost, and redundancy to choose source ranges under a hard token cap.
9. **Adapters** expose evidence through Python, JSON/Markdown, CLI, MCP, and a read-only local dashboard.
10. **Graph-artifact pipeline** uses Tree-sitter extraction, NetworkX resolution and clustering,
    deterministic analysis, and JSON/Markdown/HTML exports for graph-first exploration.

## Data flow

```text
repository -> incremental parser -> SQLite units + FTS + graph + embeddings + history
task -> route -> retrieve anchors -> bounded graph/test/history expansion
     -> evolve query once -> rerank -> optimize -> evidence package + trace

repository -> detect -> Tree-sitter extract -> NetworkX build -> cluster -> analyze
           -> graph.json + GRAPH_REPORT.md + graph.html -> query/path/explain
```

Every selected item retains its file, symbol, source range, content hash, score, retrieval provenance, explanation, and a stable pointer to the full source unit.

## Package boundaries

```text
src/contextforge/
  parsers/       language-specific extraction
  indexing/      traversal and incremental indexing
  graph/         graph construction and queries
  codegraph/     portable Tree-sitter/NetworkX graph-artifact pipeline
  bundled_skills/ project-scoped graph exploration skill
  retrieval/     lexical, symbol, semantic, history, and tests
  routing/       task classification and source selection
  reranking/     candidate score fusion
  optimization/  strict token-budget selection
  context/       package assembly and rendering
  storage/       SQLite schema and repositories
  evaluation/    metrics, baselines, and ablations
  mcp/           Model Context Protocol adapter
  dashboard/     real-output visualization
```

## Trust boundaries

Repository contents and Git metadata are untrusted input. Indexing and graph mapping never execute
target code. Path resolution prevents traversal outside the selected repository. Graph artifacts
are written only beneath the repository. MCP retrieval tools are read-only except for explicit
indexing, which writes only the repository-local index.
