"""Benchmark harness for baselines, retrieval stacks, and ablations."""

from __future__ import annotations

import platform
import time
import tracemalloc
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from contextforge import ContextForge
from contextforge.evaluation.metrics import compute_metrics, mean_metrics
from contextforge.evaluation.models import (
    Ablation,
    AggregateResult,
    EvaluationConfig,
    EvaluationItem,
    EvaluationRun,
    IndexMeasurement,
    TaskEvaluation,
    TaskSpec,
)
from contextforge.models import EdgeType, NodeType
from contextforge.optimization import BudgetOptimizer
from contextforge.optimization.selector import candidate_render_cost
from contextforge.reranking import WeightedReranker
from contextforge.retrieval import (
    GitHistoryRetriever,
    LexicalRetriever,
    QueryEvolution,
    RelatedTestRetriever,
    SemanticRetriever,
    StructuralRetriever,
    SymbolRetriever,
)
from contextforge.retrieval.models import Candidate, RetrievalSource, merge_candidates
from contextforge.retrieval.text import query_terms
from contextforge.routing import AdaptiveRouter, RetrievalRoute, RouteSource, TaskType

ALL_CONFIGS = tuple(EvaluationConfig)


class Evaluator:
    """Evaluate ContextForge configurations against repository evidence gold labels."""

    def __init__(self, dataset: Path) -> None:
        self.dataset = dataset.resolve(strict=True)
        self.tasks = self._load_tasks(self.dataset)

    def evaluate(
        self,
        *,
        configurations: tuple[EvaluationConfig, ...] = ALL_CONFIGS,
        ablations: tuple[Ablation, ...] = (),
        top_k: int = 10,
        token_budget: int = 4_000,
        limit: int | None = None,
    ) -> EvaluationRun:
        """Run requested configurations and ablations with measured latency and memory."""
        tasks = self.tasks[:limit] if limit else self.tasks
        results: list[TaskEvaluation] = []
        engines: dict[Path, ContextForge] = {}
        index_measurements: list[IndexMeasurement] = []
        for task in tasks:
            repository = (self.dataset.parent / task.repository).resolve(strict=True)
            engine = engines.get(repository)
            if engine is None:
                engine = ContextForge.open(repository)
                tracemalloc.start()
                tracemalloc.reset_peak()
                started = time.perf_counter()
                report = engine.index()
                clean_latency = (time.perf_counter() - started) * 1000
                _, clean_peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                started = time.perf_counter()
                incremental = engine.index()
                incremental_latency = (time.perf_counter() - started) * 1000
                index_measurements.append(
                    IndexMeasurement(
                        repository=Path(task.repository).name,
                        files=report.source.discovered_files,
                        source_units=len(engine.database.list_units()),
                        clean_index_latency_ms=clean_latency,
                        clean_peak_memory_mb=clean_peak / 1_048_576,
                        incremental_index_latency_ms=incremental_latency,
                        incremental_files_reparsed=incremental.source.parsed_files,
                        graph_nodes=report.graph_nodes,
                        graph_edges=report.graph_edges,
                        commits=report.commits_indexed,
                    )
                )
                engines[repository] = engine
            for configuration in configurations:
                results.append(
                    self._evaluate_one(
                        engine,
                        task,
                        configuration,
                        ablation=None,
                        top_k=top_k,
                        token_budget=token_budget,
                    )
                )
            for ablation in ablations:
                results.append(
                    self._evaluate_one(
                        engine,
                        task,
                        EvaluationConfig.FULL,
                        ablation=ablation,
                        top_k=top_k,
                        token_budget=token_budget,
                    )
                )
        aggregates: list[AggregateResult] = []
        keys = list(dict.fromkeys((result.configuration, result.ablation) for result in results))
        for configuration, aggregate_ablation in keys:
            group = [
                result.metrics
                for result in results
                if result.configuration is configuration and result.ablation is aggregate_ablation
            ]
            aggregates.append(
                AggregateResult(
                    configuration=configuration,
                    ablation=aggregate_ablation,
                    task_count=len(group),
                    metrics=mean_metrics(group),
                )
            )
        return EvaluationRun(
            dataset_path=self.dataset.name,
            dataset_sha256=sha256(self.dataset.read_bytes()).hexdigest(),
            run_at=datetime.now(UTC),
            python_version=platform.python_version(),
            platform=platform.platform(),
            top_k=top_k,
            token_budget=token_budget,
            index_measurements=tuple(index_measurements),
            results=tuple(results),
            aggregates=tuple(aggregates),
        )

    def _evaluate_one(
        self,
        engine: ContextForge,
        task: TaskSpec,
        configuration: EvaluationConfig,
        *,
        ablation: Ablation | None,
        top_k: int,
        token_budget: int,
    ) -> TaskEvaluation:
        tracemalloc.start()
        tracemalloc.reset_peak()
        started = time.perf_counter()
        items, graph_expansions = self._retrieve(
            engine,
            task.task,
            configuration,
            ablation=ablation,
            token_budget=token_budget,
            top_k=top_k,
        )
        latency = (time.perf_counter() - started) * 1000
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        metrics = compute_metrics(
            task,
            items,
            top_k=top_k,
            latency_ms=latency,
            peak_memory_mb=peak / 1_048_576,
            graph_expansions=graph_expansions,
        )
        return TaskEvaluation(
            task_id=task.id,
            configuration=configuration,
            ablation=ablation,
            metrics=metrics,
            selected=tuple(items[:top_k]),
        )

    def _retrieve(
        self,
        engine: ContextForge,
        task: str,
        configuration: EvaluationConfig,
        *,
        ablation: Ablation | None,
        token_budget: int,
        top_k: int,
    ) -> tuple[list[EvaluationItem], int]:
        if configuration is EvaluationConfig.FULL and ablation is None:
            package = engine.compile_context(task=task, token_budget=token_budget)
            return (
                [
                    EvaluationItem(
                        file=item.file,
                        symbol=item.symbol,
                        start_line=item.start_line,
                        end_line=item.end_line,
                        score=item.score,
                        estimated_tokens=item.estimated_tokens,
                        sources=item.retrieved_by,
                    )
                    for item in package.items
                ],
                package.graph_expansion_count,
            )
        if configuration is EvaluationConfig.FILENAME:
            terms = set(query_terms(task))
            candidates = []
            for unit in engine.database.list_units(node_types=(NodeType.FILE,)):
                path_terms = set(query_terms(unit.path))
                score = len(terms & path_terms) / max(1, len(path_terms))
                candidate = Candidate(unit=unit, score=score)
                candidate.add_signal(
                    RetrievalSource.PATH,
                    score,
                    "Filename token-overlap baseline.",
                )
                candidates.append(candidate)
            candidates.sort(key=lambda candidate: (-candidate.score, candidate.unit.path))
            return self._items(candidates[:top_k]), 0

        use_semantic = (
            configuration is not EvaluationConfig.BM25 and ablation is not Ablation.SEMANTIC
        )
        groups = []
        if configuration is not EvaluationConfig.SEMANTIC:
            groups.extend(
                [
                    LexicalRetriever(engine.database).search(task, limit=40),
                    SymbolRetriever(engine.database).search(task, limit=20),
                ]
            )
        if use_semantic and engine.embedding_provider:
            groups.append(
                SemanticRetriever(engine.database, engine.embedding_provider).search(task, limit=40)
            )
        candidates = merge_candidates(groups)
        route = AdaptiveRouter().route(task)
        if ablation is Ablation.ROUTING:
            route = RetrievalRoute(
                retrieval_needed=True,
                task_type=TaskType.GENERAL,
                selected_sources=tuple(RouteSource),
                reasoning_summary="Evaluation ablation enables every source without routing.",
                matched_rules=("routing_ablation",),
            )
        ranked = WeightedReranker(
            redundancy_penalty=ablation is not Ablation.REDUNDANCY_PENALTY
        ).rerank(candidates, task=task, route=route)
        graph_count = 0
        use_graph = (
            configuration
            in {
                EvaluationConfig.HYBRID_GRAPH,
                EvaluationConfig.HYBRID_GRAPH_HISTORY,
                EvaluationConfig.FULL,
            }
            and ablation is not Ablation.GRAPH
        )
        expanded: list[Candidate] = []
        if use_graph:
            expanded = StructuralRetriever(engine.database).expand(
                ranked[:8],
                edge_types={
                    EdgeType.CALLS,
                    EdgeType.IMPORTS,
                    EdgeType.INHERITS,
                    EdgeType.DEFINES,
                    EdgeType.REFERENCES,
                },
                max_depth=2,
                max_nodes=40,
            )
            graph_count = len(expanded)
        tests: list[Candidate] = []
        if configuration is EvaluationConfig.FULL and ablation is not Ablation.TEST_DISCOVERY:
            tests = RelatedTestRetriever(engine.database).find(
                [candidate.unit for candidate in ranked[:8]], task=task
            )
        evolved: list[Candidate] = []
        if configuration is EvaluationConfig.FULL and ablation is not Ablation.QUERY_EVOLUTION:
            evolution = QueryEvolution(engine.database).evolve(task, ranked)
            if evolution.derived_concepts:
                evolved = LexicalRetriever(engine.database).search(
                    evolution.evolved_query, limit=20
                )
                for candidate in evolved:
                    candidate.add_signal(
                        RetrievalSource.QUERY_EVOLUTION,
                        max(candidate.source_scores.values(), default=0.0) * 0.7,
                        "Evaluation query-evolution pass.",
                    )
        history_candidates: list[Candidate] = []
        use_history = (
            configuration
            in {
                EvaluationConfig.HYBRID_GRAPH_HISTORY,
                EvaluationConfig.FULL,
            }
            and ablation is not Ablation.HISTORY
        )
        if use_history:
            commits = GitHistoryRetriever(
                engine.database, provider=engine.embedding_provider
            ).search(task, anchor_paths={candidate.unit.path for candidate in ranked[:8]})
            by_path = {
                unit.path: unit for unit in engine.database.list_units(node_types=(NodeType.FILE,))
            }
            for commit in commits:
                for path in commit.changed_files:
                    matched_unit = by_path.get(path)
                    if matched_unit:
                        candidate = Candidate(unit=matched_unit)
                        candidate.add_signal(
                            RetrievalSource.GIT_HISTORY,
                            commit.score,
                            f"Changed in relevant commit {commit.commit_hash[:10]}.",
                        )
                        history_candidates.append(candidate)
        merged = merge_candidates([candidates, expanded, tests, evolved, history_candidates])
        final = WeightedReranker(
            redundancy_penalty=ablation is not Ablation.REDUNDANCY_PENALTY
        ).rerank(merged, task=task, route=route)
        if configuration in {EvaluationConfig.BM25, EvaluationConfig.SEMANTIC}:
            selected = final[:top_k]
        elif ablation is Ablation.TOKEN_OPTIMIZATION:
            selected = []
            used = 0
            for candidate in final:
                cost = candidate_render_cost(candidate)
                if used + cost <= token_budget:
                    selected.append(candidate)
                    used += cost
        else:
            selected = list(
                BudgetOptimizer(redundancy_penalty=ablation is not Ablation.REDUNDANCY_PENALTY)
                .select(final, token_budget=token_budget)
                .selected
            )
        return self._items(selected), graph_count

    @staticmethod
    def _items(candidates: list[Candidate]) -> list[EvaluationItem]:
        return [
            EvaluationItem(
                file=candidate.unit.path,
                symbol=candidate.unit.qualname,
                start_line=candidate.unit.start_line,
                end_line=candidate.unit.end_line,
                score=candidate.score,
                estimated_tokens=candidate_render_cost(candidate),
                sources=tuple(candidate.retrieved_by),
            )
            for candidate in candidates
        ]

    @staticmethod
    def _load_tasks(dataset: Path) -> list[TaskSpec]:
        tasks: list[TaskSpec] = []
        for line_number, line in enumerate(
            dataset.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                tasks.append(TaskSpec.model_validate_json(line))
            except ValueError as error:
                raise ValueError(f"Invalid dataset line {line_number}: {error}") from error
        if not tasks:
            raise ValueError("Evaluation dataset contains no tasks")
        return tasks
