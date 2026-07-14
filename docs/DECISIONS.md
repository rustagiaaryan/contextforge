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

## ADR-007: Git memory needs a semantic gate, not only file overlap

**Decision:** A historical commit must share task language in its message or have unusually strong semantic similarity plus an anchor-file overlap. File overlap, recency, or a path keyword alone cannot pass the gate.

**Why:** Old commits frequently touch current hotspots without addressing the current behavior. Loose overlap polluted the fixture benchmark; the stronger gate preserved the controlled regression patch while excluding repository-setup history.

## ADR-008: The dashboard is a read model over evidence packages

**Decision:** The local FastAPI dashboard consumes `EvidencePackage`, index-status, and graph APIs directly. It has no independent retrieval implementation or database schema.

**Why:** A visualization that recomputes or mocks scores can diverge from CLI/MCP behavior. A thin read model makes the interface a debugging instrument for the actual compiler.
