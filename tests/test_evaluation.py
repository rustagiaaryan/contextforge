from __future__ import annotations

import json
from pathlib import Path

from contextforge.evaluation import Ablation, EvaluationConfig, Evaluator
from contextforge.evaluation.metrics import compute_metrics
from contextforge.evaluation.models import EvaluationItem, TaskSpec

ROOT = Path(__file__).parents[1]
DATASET = ROOT / "benchmarks" / "sample_tasks.jsonl"


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
        )
    ]

    metrics = compute_metrics(
        task,
        selected,
        top_k=3,
        latency_ms=1.0,
        peak_memory_mb=2.0,
        graph_expansions=0,
    )

    assert metrics.file_recall_at_k == 1 / 3
    assert metrics.file_precision_at_k == 1 / 3
    assert metrics.symbol_recall_at_k == 1 / 3
    assert metrics.mrr == 1.0
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
    assert run.dataset_sha256
    assert all(result.metrics.retrieval_latency_ms > 0 for result in run.results)
    assert any(result.ablation is Ablation.GRAPH for result in run.results)
    json.loads(run.model_dump_json())
