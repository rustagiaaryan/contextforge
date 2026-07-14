"""Transparent weighted candidate reranking."""

from __future__ import annotations

import math
from pathlib import PurePosixPath

from contextforge.models import NodeType
from contextforge.retrieval.models import Candidate, RetrievalSource
from contextforge.retrieval.text import query_terms
from contextforge.routing import RetrievalRoute

SOURCE_WEIGHTS: dict[RetrievalSource, float] = {
    RetrievalSource.LEXICAL: 1.0,
    RetrievalSource.SYMBOL: 0.95,
    RetrievalSource.SEMANTIC: 0.78,
    RetrievalSource.CALL_GRAPH: 0.86,
    RetrievalSource.IMPORT_GRAPH: 0.72,
    RetrievalSource.INHERITANCE_GRAPH: 0.76,
    RetrievalSource.GRAPH: 0.62,
    RetrievalSource.RELATED_TESTS: 0.88,
    RetrievalSource.GIT_HISTORY: 0.6,
    RetrievalSource.HOTSPOT: 0.42,
    RetrievalSource.QUERY_EVOLUTION: 0.7,
    RetrievalSource.PATH: 0.65,
}


class WeightedReranker:
    """Fuse normalized retrieval evidence without claiming a trained model."""

    def __init__(self, *, redundancy_penalty: bool = True) -> None:
        self.redundancy_penalty = redundancy_penalty

    def rerank(
        self, candidates: list[Candidate], *, task: str, route: RetrievalRoute
    ) -> list[Candidate]:
        """Score source relevance, agreement, paths, tests, graph distance, and cost."""
        terms = set(query_terms(task))
        reranked = [candidate.model_copy(deep=True) for candidate in candidates]
        for candidate in reranked:
            weighted = [
                SOURCE_WEIGHTS[source] * score for source, score in candidate.source_scores.items()
            ]
            strongest = max(weighted, default=0.0)
            agreement = 1.0 - math.prod(1.0 - min(0.95, value) for value in weighted)
            score = strongest * 0.62 + agreement * 0.28
            if candidate.metadata.get("exact_symbol_match") is True:
                score += 0.1
                candidate.reasons.append("Reranker bonus: exact symbol match.")
            path_terms = {
                part.lower()
                for part in PurePosixPath(candidate.unit.path).parts
                for part in part.replace(".", "_").split("_")
                if len(part) > 2
            }
            path_overlap = terms.intersection(path_terms)
            if path_overlap:
                bonus = min(0.1, len(path_overlap) * 0.04)
                score += bonus
                candidate.source_scores[RetrievalSource.PATH] = bonus
                if RetrievalSource.PATH not in candidate.retrieved_by:
                    candidate.retrieved_by.append(RetrievalSource.PATH)
                candidate.reasons.append(
                    f"Reranker bonus: path matches {', '.join(sorted(path_overlap))}."
                )
            if candidate.unit.node_type is NodeType.TEST:
                if RetrievalSource.RELATED_TESTS in candidate.retrieved_by:
                    score += 0.08
                    candidate.reasons.append("Reranker bonus: deliberate validation evidence.")
                else:
                    score += 0.01
            if candidate.graph_distance is not None:
                distance_penalty = min(0.12, candidate.graph_distance * 0.035)
                score -= distance_penalty
                candidate.metadata["graph_distance_penalty"] = distance_penalty
            cost_penalty = min(0.09, math.log1p(candidate.unit.estimated_tokens) / 100.0)
            score -= cost_penalty
            candidate.metadata["token_cost_penalty"] = cost_penalty
            candidate.score = min(1.0, max(0.0, score))

        reranked.sort(key=self._sort_key)
        if self.redundancy_penalty:
            self._apply_redundancy_penalties(reranked)
            reranked.sort(key=self._sort_key)
        return reranked

    @staticmethod
    def _apply_redundancy_penalties(candidates: list[Candidate]) -> None:
        accepted: list[Candidate] = []
        for candidate in candidates:
            maximum_overlap = 0.0
            for previous in accepted:
                if candidate.unit.path != previous.unit.path:
                    continue
                intersection = max(
                    0,
                    min(candidate.unit.end_line, previous.unit.end_line)
                    - max(candidate.unit.start_line, previous.unit.start_line)
                    + 1,
                )
                length = max(1, candidate.unit.end_line - candidate.unit.start_line + 1)
                maximum_overlap = max(maximum_overlap, intersection / length)
            if maximum_overlap >= 0.8:
                penalty = min(0.18, maximum_overlap * 0.14)
                candidate.score = max(0.0, candidate.score - penalty)
                candidate.metadata["redundancy_penalty"] = penalty
                candidate.reasons.append(
                    f"Reranker penalty: {maximum_overlap:.0%} range overlap with stronger evidence."
                )
            accepted.append(candidate)

    @staticmethod
    def _sort_key(candidate: Candidate) -> tuple[float, int, str, int]:
        return (
            -candidate.score,
            candidate.unit.estimated_tokens,
            candidate.unit.path,
            candidate.unit.start_line,
        )
