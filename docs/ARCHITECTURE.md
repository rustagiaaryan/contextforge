# ContextForge Architecture

## Objective

ContextForge compiles task-specific repository evidence under a strict token budget. It is a library first; the CLI, MCP server, and dashboard are adapters over the same engine.

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

## Data flow

```text
repository -> incremental parser -> SQLite units + FTS + graph + embeddings + history
task -> route -> retrieve anchors -> bounded graph/test/history expansion
     -> evolve query once -> rerank -> optimize -> evidence package + trace
```

Every selected item retains its file, symbol, source range, content hash, score, retrieval provenance, explanation, and a stable pointer to the full source unit.

## Package boundaries

```text
src/contextforge/
  parsers/       language-specific extraction
  indexing/      traversal and incremental indexing
  graph/         graph construction and queries
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

Repository contents and Git metadata are untrusted input. Indexing never executes target code. Path resolution prevents traversal outside the selected repository. MCP retrieval tools are read-only except for the explicit indexing operation, which writes only the repository-local index.

