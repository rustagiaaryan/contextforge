# Implementation Plan

This is a living checklist. A checked box means implementation and proportionate tests exist, not merely that a file was created.

## Phase 0 — foundation

- [x] Audit workspace and GitHub availability
- [x] Establish architecture, decisions, evaluation, demo, and security documents
- [x] Configure package, lint, type checking, tests, CI, Docker, and ignore rules
- [x] Publish initial Git milestone

## Phase 1 — parser and persistent index

- [x] Ignore-aware traversal and Python AST extraction
- [x] SQLite schema and content-hash incremental reindexing
- [x] Parser and incremental-index tests

## Phase 2 — knowledge graph

- [x] Typed nodes and edges
- [x] Containment, definition, import, inheritance, call, and reference edges
- [x] Graph query tests

## Phase 3 — lexical and symbol retrieval

- [x] FTS/BM25 search across paths, symbols, docs, comments, and code
- [x] Exact and fuzzy symbol search with provenance
- [x] Retrieval latency benchmark

## Phase 4 — semantic retrieval

- [x] Pluggable embedding provider and deterministic local default
- [x] Batched, content-addressed cache and cosine search
- [x] Graceful provider failure

## Phase 5 — structural retrieval and tests

- [x] Bounded, edge-aware graph expansion
- [x] Multi-signal related-test discovery

## Phase 6 — Git memory

- [x] Commit, diff-summary, hotspot, and co-change indexing
- [x] Confidence-gated history retrieval

## Phase 7 — routing, reranking, and query evolution

- [x] Explainable adaptive router
- [x] Unified deterministic reranker
- [x] One bounded query-evolution pass with trace

## Phase 8 — context optimization

- [x] Strict token estimator and diversity-aware selection
- [x] JSON and Markdown evidence packages

## Phase 9 — interfaces

- [x] Python API and polished CLI
- [x] Typed MCP tools and sample configuration

## Phase 10 — evaluation

- [x] Fixture task format, baselines, metrics, and ablations
- [x] Checked-in compact measured results
- [x] Pinned real historical-patch benchmark with token-reduction and package-recall metrics

## Phase 11 — dashboard and demo

- [x] Real-output dashboard with retrieval trace and graph
- [x] Reproducible local demonstration

## Phase 12 — hardening and release

- [x] Full local and clean-clone validation
- [x] Latency and memory measurements
- [x] Secret and path audit
- [x] Release notes and initial tag
- [x] Clean tree and synchronized remote

## Phase 13 — graph-first multi-language workflow

- [x] Tree-sitter discovery and shared extraction across 26 grammar entry points
- [x] Plain extraction schema with extracted, inferred, and ambiguous confidence labels
- [x] NetworkX resolution, community detection, centrality, and cross-community analysis
- [x] Portable graph JSON, Markdown report, and standalone interactive HTML
- [x] Fuzzy graph query, shortest-path, and node-explain CLI commands
- [x] Validated project-scoped agent skill and installer
- [x] Mixed Python/TypeScript/Go semantic fixture and all-grammar smoke test
