# Release notes

## Unreleased

- Added a graph-first `detect → extract → build → cluster → analyze → export` workflow using
  Tree-sitter, NetworkX, NumPy, and RapidFuzz.
- Added confidence-tagged portable `graph.json`, `GRAPH_REPORT.md`, and interactive `graph.html`
  artifacts plus graph query, path, and explain commands.
- Added 26 grammar entry points, mixed Python/TypeScript/Go semantic fixtures, and a validated
  project-scoped agent skill installer.
- Added a pinned, network-opt-in historical-patch benchmark covering 12 real Click, HTTPX, and
  Typer fixes, with exact patch-label verification and whole-repository token baselines.
- Added package Hit/Recall/Precision, complete recall, tokens saved, reduction rate, and explicit
  memory-tracing metadata to evaluation output.
- Hardened Python parsing for overloads/conditional duplicate definitions and replaced repeated
  AST source rescans with byte-offset slicing.
- Bounded co-change inference for mass migrations while retaining their commit/file history.
- Measured 11/12 package hits, 69.4% average fix-file recall, and 96.8% estimated token reduction
  for the full adaptive pipeline; these are retrieval-proxy metrics, not patch success.

## v0.1.0 — Initial alpha

ContextForge v0.1.0 establishes a fully local, Python-first repository-context compiler.

### Included

- Incremental ignore-aware parsing and content-addressed SQLite/FTS5 storage
- Typed code/Git knowledge graph with bounded structural queries
- BM25, fuzzy symbols, deterministic local embeddings, test discovery, and gated history
- Adaptive routing, one-pass query evolution, explainable reranking, and strict-budget selection
- JSON/Markdown packages through Python, CLI, eleven MCP tools, and a real-output dashboard
- Seven evaluation configurations, eight ablations, compact preliminary results, and performance measurements
- CI, Docker, locked dependencies, strict typing, security/configuration documentation, and fixture integration tests

### Known limits

Python is the only first-class language, dynamic call edges are best-effort, feature hashing is not a trained embedding model, and the included benchmark is too small to establish general retrieval quality. See the README limitations and roadmap before using v0.1.0 as a production service.

### Release validation

The release was rebuilt from a fresh public GitHub clone. Formatting, linting, strict typing, 35 tests, 90% statement coverage, wheel/sdist contents, Docker build/run, dependency audit, dashboard API, full fixture benchmark, and an actual MCP stdio handshake all passed. Secret and machine-path scans found no tracked matches.
