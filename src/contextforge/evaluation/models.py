"""Typed evaluation dataset and result models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from contextforge.retrieval.models import RetrievalSource


class EvaluationConfig(StrEnum):
    """Required baseline and ContextForge retrieval configurations."""

    FILENAME = "filename_baseline"
    BM25 = "bm25_only"
    SEMANTIC = "semantic_only"
    HYBRID = "hybrid"
    HYBRID_GRAPH = "hybrid_graph"
    HYBRID_GRAPH_HISTORY = "hybrid_graph_history"
    FULL = "full_adaptive"


class Ablation(StrEnum):
    """Full-pipeline components that can be disabled independently."""

    SEMANTIC = "without_semantic"
    GRAPH = "without_graph"
    HISTORY = "without_history"
    TEST_DISCOVERY = "without_test_discovery"
    QUERY_EVOLUTION = "without_query_evolution"
    ROUTING = "without_routing"
    TOKEN_OPTIMIZATION = "without_token_optimization"
    REDUNDANCY_PENALTY = "without_redundancy_penalty"


class GoldLineRange(BaseModel):
    """An optional answer-bearing source range."""

    model_config = ConfigDict(frozen=True)

    file: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)


class TaskSpec(BaseModel):
    """One benchmark task and its gold repository evidence."""

    model_config = ConfigDict(frozen=True)

    id: str
    repository: str
    task: str
    gold_files: tuple[str, ...]
    gold_symbols: tuple[str, ...] = ()
    gold_line_ranges: tuple[GoldLineRange, ...] = ()
    metadata: dict[str, object] = Field(default_factory=dict)


class EvaluationItem(BaseModel):
    """Normalized selected evidence from any evaluated strategy."""

    model_config = ConfigDict(frozen=True)

    file: str
    symbol: str
    start_line: int
    end_line: int
    score: float
    estimated_tokens: int
    sources: tuple[RetrievalSource, ...] = ()


class Metrics(BaseModel):
    """Retrieval quality, context cost, and performance metrics."""

    model_config = ConfigDict(frozen=True)

    file_recall_at_k: float
    file_precision_at_k: float
    symbol_recall_at_k: float
    symbol_precision_at_k: float
    mrr: float
    ndcg_at_k: float
    gold_line_coverage: float
    context_tokens: int
    tokens_per_relevant_file: float
    retrieval_latency_ms: float
    peak_memory_mb: float
    graph_expansions: int
    evidence_source_diversity: int
    selected_context_relevance: float


class TaskEvaluation(BaseModel):
    """Metrics for one task/configuration pair."""

    model_config = ConfigDict(frozen=True)

    task_id: str
    configuration: EvaluationConfig
    ablation: Ablation | None = None
    metrics: Metrics
    selected: tuple[EvaluationItem, ...]


class AggregateResult(BaseModel):
    """Mean metrics for a configuration or ablation."""

    model_config = ConfigDict(frozen=True)

    configuration: EvaluationConfig
    ablation: Ablation | None = None
    task_count: int
    metrics: Metrics


class IndexMeasurement(BaseModel):
    """Measured clean/incremental repository indexing performance."""

    model_config = ConfigDict(frozen=True)

    repository: str
    files: int
    source_units: int
    clean_index_latency_ms: float
    clean_peak_memory_mb: float
    incremental_index_latency_ms: float
    incremental_files_reparsed: int
    graph_nodes: int
    graph_edges: int
    commits: int


class EvaluationRun(BaseModel):
    """Reproducible benchmark run with task-level and aggregate results."""

    model_config = ConfigDict(frozen=True)

    dataset_path: str
    dataset_sha256: str
    run_at: datetime
    python_version: str
    platform: str
    top_k: int
    token_budget: int
    index_measurements: tuple[IndexMeasurement, ...]
    results: tuple[TaskEvaluation, ...]
    aggregates: tuple[AggregateResult, ...]
