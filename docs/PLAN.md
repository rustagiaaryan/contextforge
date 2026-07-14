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

- [ ] Typed nodes and edges
- [ ] Containment, definition, import, inheritance, call, and reference edges
- [ ] Graph query tests

## Phase 3 — lexical and symbol retrieval

- [ ] FTS/BM25 search across paths, symbols, docs, comments, and code
- [ ] Exact and fuzzy symbol search with provenance
- [ ] Retrieval latency benchmark

## Phase 4 — semantic retrieval

- [ ] Pluggable embedding provider and deterministic local default
- [ ] Batched, content-addressed cache and cosine search
- [ ] Graceful provider failure

## Phase 5 — structural retrieval and tests

- [ ] Bounded, edge-aware graph expansion
- [ ] Multi-signal related-test discovery

## Phase 6 — Git memory

- [ ] Commit, diff-summary, hotspot, and co-change indexing
- [ ] Confidence-gated history retrieval

## Phase 7 — routing, reranking, and query evolution

- [ ] Explainable adaptive router
- [ ] Unified deterministic reranker
- [ ] One bounded query-evolution pass with trace

## Phase 8 — context optimization

- [ ] Strict token estimator and diversity-aware selection
- [ ] JSON and Markdown evidence packages

## Phase 9 — interfaces

- [ ] Python API and polished CLI
- [ ] Typed MCP tools and sample configuration

## Phase 10 — evaluation

- [ ] Fixture task format, baselines, metrics, and ablations
- [ ] Checked-in compact measured results

## Phase 11 — dashboard and demo

- [ ] Real-output dashboard with retrieval trace and graph
- [ ] Reproducible demonstration and screenshot

## Phase 12 — hardening and release

- [ ] Full local and clean-clone validation
- [ ] Latency and memory measurements
- [ ] Secret and path audit
- [ ] Release notes and initial tag
- [ ] Clean tree and synchronized remote
