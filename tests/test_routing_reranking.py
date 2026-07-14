from __future__ import annotations

import shutil
from pathlib import Path

from contextforge.graph import GraphBuilder
from contextforge.indexing import RepositoryIndexer
from contextforge.reranking import WeightedReranker
from contextforge.retrieval import LexicalRetriever, QueryEvolution, SymbolRetriever
from contextforge.retrieval.models import merge_candidates
from contextforge.routing import AdaptiveRouter, RouteSource, TaskType
from contextforge.storage import Database

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"


def _database(tmp_path: Path) -> Database:
    repository = tmp_path / "repository"
    shutil.copytree(FIXTURE, repository)
    database = Database(tmp_path / "index.sqlite3")
    RepositoryIndexer(repository, database).index()
    GraphBuilder(repository, database).build()
    return database


def test_router_selects_cross_file_bug_sources_explainably() -> None:
    route = AdaptiveRouter().route(
        "Requests through mounted sub-applications lose their route prefix."
    )

    assert route.retrieval_needed
    assert route.task_type is TaskType.CROSS_FILE_BUG
    assert RouteSource.CALL_GRAPH in route.selected_sources
    assert RouteSource.RELATED_TESTS in route.selected_sources
    assert RouteSource.GIT_HISTORY in route.selected_sources
    assert "cross_file_terms" in route.matched_rules


def test_weighted_reranker_rewards_evidence_agreement_and_explains_cost(tmp_path: Path) -> None:
    database = _database(tmp_path)
    task = "Mount.resolve loses route prefix"
    candidates = merge_candidates(
        [LexicalRetriever(database).search(task), SymbolRetriever(database).search(task)]
    )

    results = WeightedReranker().rerank(candidates, task=task, route=AdaptiveRouter().route(task))

    assert results[0].unit.qualname == "app.routing.Mount.resolve"
    assert len(results[0].retrieved_by) >= 2
    assert 0.0 <= results[0].score <= 1.0
    assert "token_cost_penalty" in results[0].metadata


def test_query_evolution_is_single_pass_and_strictly_bounded(tmp_path: Path) -> None:
    database = _database(tmp_path)
    task = "mounted prefix regression"
    candidates = LexicalRetriever(database).search(task)
    for index, candidate in enumerate(candidates):
        candidate.score = 1.0 - index * 0.01

    trace = QueryEvolution(database).evolve(task, candidates, max_anchors=2, max_concepts=4)

    assert trace.anchors_examined <= 2
    assert len(trace.derived_concepts) <= 4
    assert trace.evolved_query.count("Related repository concepts:") <= 1
    assert set(trace.derived_concepts).isdisjoint(trace.original_terms)
