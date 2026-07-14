# Evaluation

Evaluation is a product feature: every retrieval component should justify the context it consumes.

## Dataset format

Each JSONL task identifies a repository, natural-language task, gold files, optional gold symbols and line ranges, and metadata. Fixture repositories keep CI deterministic; external benchmark downloads are opt-in.

## Compared configurations

The harness will evaluate filename/random baseline, BM25, semantic-only, hybrid, hybrid plus graph, hybrid plus graph/history, and the full adaptive pipeline. Ablations will individually disable semantics, graph expansion, history, test discovery, query evolution, routing, token optimization, and redundancy penalties.

## Metrics

- File and symbol Precision/Recall@K, MRR, and NDCG
- Gold-line coverage and selected-context relevance
- Context token count and tokens per relevant file
- Index/retrieval latency, peak memory, and graph expansion count
- Evidence-source diversity

## Claim policy

Checked-in summaries must contain the command, environment, timestamp, dataset hash, configuration, and raw aggregate values. Results are labelled **measured**, **preliminary**, or **external**. Missing experiments remain goals; they are never inferred or fabricated.

No results have been measured yet. This document will be updated by the benchmark milestone.

