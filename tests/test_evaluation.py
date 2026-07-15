from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

from contextforge.evaluation import Ablation, EvaluationConfig, Evaluator
from contextforge.evaluation.metrics import compute_metrics
from contextforge.evaluation.models import (
    EvaluationItem,
    HistoricalBenchmarkRun,
    TaskSpec,
)

ROOT = Path(__file__).parents[1]
DATASET = ROOT / "benchmarks" / "sample_tasks.jsonl"
HISTORICAL_MANIFEST = ROOT / "benchmarks" / "historical_patches.jsonl"
HISTORICAL_RESULT = ROOT / "benchmarks" / "results" / "historical_patches.json"


def test_metrics_compute_exact_file_symbol_ranking_and_line_coverage() -> None:
    task = TaskSpec.model_validate_json(DATASET.read_text().splitlines()[0])
    selected = [
        EvaluationItem(
            file="app/routing.py",
            symbol="app.routing.Mount.resolve",
            start_line=7,
            end_line=19,
            score=1.0,
            estimated_tokens=100,
        ),
        EvaluationItem(
            file="app/other.py",
            symbol="app.other.unrelated",
            start_line=1,
            end_line=2,
            score=0.1,
            estimated_tokens=50,
        ),
    ]

    metrics = compute_metrics(
        task,
        selected,
        top_k=3,
        latency_ms=1.0,
        peak_memory_mb=2.0,
        graph_expansions=0,
        repository_source_tokens=1_000,
    )

    assert metrics.file_recall_at_k == 1 / 3
    assert metrics.file_precision_at_k == 1 / 3
    assert metrics.file_hit_at_k == 1.0
    assert metrics.complete_file_recall_at_k == 0.0
    assert metrics.package_file_recall == 1 / 3
    assert metrics.package_file_hit == 1.0
    assert metrics.package_complete_file_recall == 0.0
    assert metrics.symbol_recall_at_k == 1 / 3
    assert metrics.mrr == 1.0
    assert metrics.context_tokens == 150
    assert metrics.tokens_saved == 850
    assert metrics.token_reduction_fraction == 0.85
    assert metrics.selected_item_count == 2
    assert metrics.selected_file_count == 2
    assert 0.0 < metrics.gold_line_coverage < 1.0


def test_evaluator_runs_required_configs_and_an_ablation() -> None:
    run = Evaluator(DATASET).evaluate(
        configurations=(
            EvaluationConfig.FILENAME,
            EvaluationConfig.BM25,
            EvaluationConfig.FULL,
        ),
        ablations=(Ablation.GRAPH,),
        top_k=5,
        token_budget=1_200,
        limit=1,
    )

    assert len(run.results) == 4
    assert len(run.aggregates) == 4
    assert len(run.index_measurements) == 1
    assert run.index_measurements[0].incremental_files_reparsed == 0
    assert run.index_measurements[0].repository_source_tokens > 0
    assert run.dataset_sha256
    assert run.memory_tracing_enabled
    assert all(result.metrics.retrieval_latency_ms > 0 for result in run.results)
    assert any(result.ablation is Ablation.GRAPH for result in run.results)
    json.loads(run.model_dump_json())


def test_checked_historical_claims_match_pinned_manifest() -> None:
    run = HistoricalBenchmarkRun.model_validate_json(HISTORICAL_RESULT.read_text())
    assert run.manifest_sha256 == sha256(HISTORICAL_MANIFEST.read_bytes()).hexdigest()
    assert run.task_count == 12
    full = next(
        aggregate
        for aggregate in run.evaluation.aggregates
        if aggregate.configuration is EvaluationConfig.FULL
    )
    assert full.metrics.package_file_hit == 11 / 12
    assert full.metrics.package_file_recall == pytest.approx(0.6944444444)
    assert full.metrics.token_reduction_fraction == pytest.approx(0.9683498294)
    full_tasks = [
        result for result in run.evaluation.results if result.configuration is EvaluationConfig.FULL
    ]
    assert all(
        result.metrics.context_tokens <= run.evaluation.token_budget for result in full_tasks
    )
