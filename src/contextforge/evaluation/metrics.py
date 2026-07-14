"""Deterministic retrieval metric calculations."""

from __future__ import annotations

import math

from contextforge.evaluation.models import EvaluationItem, Metrics, TaskSpec


def compute_metrics(
    task: TaskSpec,
    selected: list[EvaluationItem],
    *,
    top_k: int,
    latency_ms: float,
    peak_memory_mb: float,
    graph_expansions: int,
) -> Metrics:
    """Compute file/symbol/ranking/line/cost/diversity metrics for one task."""
    limited = selected[:top_k]
    ranked_files = list(dict.fromkeys(item.file for item in limited))
    ranked_symbols = list(dict.fromkeys(item.symbol for item in limited))
    gold_files = set(task.gold_files)
    gold_symbols = set(task.gold_symbols)
    relevant_files = gold_files.intersection(ranked_files)
    relevant_symbols = gold_symbols.intersection(ranked_symbols)
    file_recall = len(relevant_files) / max(1, len(gold_files))
    file_precision = len(relevant_files) / max(1, top_k)
    symbol_recall = len(relevant_symbols) / max(1, len(gold_symbols)) if gold_symbols else 0.0
    symbol_precision = len(relevant_symbols) / max(1, top_k) if gold_symbols else 0.0
    first_relevant = next(
        (index for index, path in enumerate(ranked_files, start=1) if path in gold_files), None
    )
    mrr = 1.0 / first_relevant if first_relevant else 0.0
    dcg = sum(
        1.0 / math.log2(index + 1)
        for index, path in enumerate(ranked_files[:top_k], start=1)
        if path in gold_files
    )
    ideal_count = min(top_k, len(gold_files))
    ideal = sum(1.0 / math.log2(index + 1) for index in range(1, ideal_count + 1))
    ndcg = dcg / ideal if ideal else 0.0
    gold_lines = sum(
        line_range.end_line - line_range.start_line + 1 for line_range in task.gold_line_ranges
    )
    covered_lines = 0
    for line_range in task.gold_line_ranges:
        covered: set[int] = set()
        for item in limited:
            if item.file != line_range.file:
                continue
            start = max(item.start_line, line_range.start_line)
            end = min(item.end_line, line_range.end_line)
            if start <= end:
                covered.update(range(start, end + 1))
        covered_lines += len(covered)
    line_coverage = covered_lines / gold_lines if gold_lines else 0.0
    tokens = sum(item.estimated_tokens for item in limited)
    relevant_item_count = sum(item.file in gold_files for item in limited)
    diversity = len({source for item in limited for source in item.sources})
    return Metrics(
        file_recall_at_k=file_recall,
        file_precision_at_k=file_precision,
        symbol_recall_at_k=symbol_recall,
        symbol_precision_at_k=symbol_precision,
        mrr=mrr,
        ndcg_at_k=ndcg,
        gold_line_coverage=line_coverage,
        context_tokens=tokens,
        tokens_per_relevant_file=tokens / max(1, len(relevant_files)),
        retrieval_latency_ms=latency_ms,
        peak_memory_mb=peak_memory_mb,
        graph_expansions=graph_expansions,
        evidence_source_diversity=diversity,
        selected_context_relevance=relevant_item_count / max(1, len(limited)),
    )


def mean_metrics(metrics: list[Metrics]) -> Metrics:
    """Average metric records with integer counts rounded to the nearest integer."""
    if not metrics:
        raise ValueError("Cannot aggregate an empty metric list")
    count = len(metrics)
    return Metrics(
        file_recall_at_k=sum(item.file_recall_at_k for item in metrics) / count,
        file_precision_at_k=sum(item.file_precision_at_k for item in metrics) / count,
        symbol_recall_at_k=sum(item.symbol_recall_at_k for item in metrics) / count,
        symbol_precision_at_k=sum(item.symbol_precision_at_k for item in metrics) / count,
        mrr=sum(item.mrr for item in metrics) / count,
        ndcg_at_k=sum(item.ndcg_at_k for item in metrics) / count,
        gold_line_coverage=sum(item.gold_line_coverage for item in metrics) / count,
        context_tokens=round(sum(item.context_tokens for item in metrics) / count),
        tokens_per_relevant_file=sum(item.tokens_per_relevant_file for item in metrics) / count,
        retrieval_latency_ms=sum(item.retrieval_latency_ms for item in metrics) / count,
        peak_memory_mb=sum(item.peak_memory_mb for item in metrics) / count,
        graph_expansions=round(sum(item.graph_expansions for item in metrics) / count),
        evidence_source_diversity=round(
            sum(item.evidence_source_diversity for item in metrics) / count
        ),
        selected_context_relevance=sum(item.selected_context_relevance for item in metrics) / count,
    )
