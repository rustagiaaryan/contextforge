# Architecture Decisions

## ADR-001: SQLite is the default store

**Decision:** Persist source units, graph edges, embeddings, and Git memory in one repository-local SQLite database. Use FTS5 for lexical retrieval.

**Why:** SQLite is transactional, portable, inspectable, supports incremental updates, and requires no service. A graph database was rejected for the default because its operational cost is disproportionate to bounded local graph neighborhoods.

## ADR-002: Python AST is the first parser

**Decision:** Use the standard Python AST plus tokenization for excellent Python extraction behind a language-parser protocol.

**Why:** It provides accurate line ranges and semantic constructs with no native dependency. Tree-sitter remains a planned adapter for multi-language coverage rather than a hard requirement for the Python-first release.

## ADR-003: Deterministic local embeddings are always available

**Decision:** Ship a signed feature-hashing embedder over code tokens and character n-grams. External/model providers implement the same interface.

**Why:** The default demo must require no key or model download. Hash embeddings are weaker than trained models and will be labelled accurately, but they exercise batching, caching, invalidation, and hybrid retrieval in every environment.

## ADR-004: Search anchors graph traversal

**Decision:** Structural expansion begins only from high-confidence lexical, symbol, or semantic anchors and has depth/node caps with edge and distance penalties.

**Rejected:** Whole-graph traversal, which magnifies uncertain call edges and consumes context on structurally nearby but task-irrelevant code.

## ADR-005: Explainable scoring before learned reranking

**Decision:** Normalize source scores and combine explicit weighted signals. Keep a reranker protocol for later cross-encoder, LLM, or learned implementations.

**Why:** Initial benchmark scale cannot justify claims of trained ranking. Transparent weights make ablations and failure analysis useful.

## ADR-006: Source ranges are the budget unit

**Decision:** Optimize complete symbol/file ranges, then render them without silently truncating code. Reserve package overhead before selection.

**Why:** Whole symbols are more actionable than arbitrary token fragments, and strict accounting makes budget behavior testable.

