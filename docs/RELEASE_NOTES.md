# Release notes

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

