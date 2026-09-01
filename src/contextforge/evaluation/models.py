"""Typed evaluation dataset and result models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    file_hit_at_k: float
    complete_file_recall_at_k: float
    package_file_recall: float
    package_file_precision: float
    package_file_hit: float
    package_complete_file_recall: float
    symbol_recall_at_k: float
    symbol_precision_at_k: float
    mrr: float
    ndcg_at_k: float
    gold_line_coverage: float
    context_tokens: int
    repository_source_tokens: int
    tokens_saved: int
    token_reduction_fraction: float
    selected_item_count: int
    selected_file_count: int
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
    repository_source_tokens: int
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
    memory_tracing_enabled: bool
    index_measurements: tuple[IndexMeasurement, ...]
    results: tuple[TaskEvaluation, ...]
    aggregates: tuple[AggregateResult, ...]


class HistoricalPatchSpec(BaseModel):
    """Pinned public pull request evaluated at its pre-fix repository state."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]+$")
    repository_url: str
    base_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    fix_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    task: str = Field(min_length=8)
    gold_files: tuple[str, ...] = Field(min_length=1)
    source_url: str

    @field_validator("repository_url")
    @classmethod
    def validate_repository_url(cls, value: str) -> str:
        """Limit downloads to ordinary public GitHub HTTPS repositories."""
        if not value.startswith("https://github.com/") or not value.endswith(".git"):
            raise ValueError("repository_url must be an HTTPS GitHub clone URL ending in .git")
        return value

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str) -> str:
        """Require an auditable GitHub pull-request URL."""
        if not value.startswith("https://github.com/") or "/pull/" not in value:
            raise ValueError("source_url must be a GitHub pull-request URL")
        return value

    @field_validator("gold_files")
    @classmethod
    def validate_gold_files(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Reject paths that could escape a prepared repository snapshot."""
        for value in values:
            path = Path(value)
            if path.is_absolute() or ".." in path.parts or path.suffix not in {".py", ".pyi"}:
                raise ValueError("gold_files must be relative Python source paths")
        if len(values) != len(set(values)):
            raise ValueError("gold_files must be unique")
        return values


class HistoricalBenchmarkRun(BaseModel):
    """Auditable evaluation output for a pinned historical-patch manifest."""

    model_config = ConfigDict(frozen=True)

    manifest_name: str
    manifest_sha256: str
    task_count: int
    repositories: tuple[str, ...]
    selection_policy: str
    evaluation: EvaluationRun
