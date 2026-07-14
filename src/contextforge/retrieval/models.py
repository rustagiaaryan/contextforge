"""Unified retrieval candidate schema with provenance."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from contextforge.models import EdgeType, SourceUnit


class RetrievalSource(StrEnum):
    """Supported candidate provenance labels."""

    LEXICAL = "bm25"
    SYMBOL = "symbol_search"
    SEMANTIC = "semantic"
    CALL_GRAPH = "call_graph"
    IMPORT_GRAPH = "import_graph"
    INHERITANCE_GRAPH = "inheritance_graph"
    GRAPH = "graph_expansion"
    RELATED_TESTS = "related_tests"
    GIT_HISTORY = "git_history"
    HOTSPOT = "hotspot"
    QUERY_EVOLUTION = "query_evolution"
    PATH = "path"


class Candidate(BaseModel):
    """A source range found by one or more retrieval mechanisms."""

    unit: SourceUnit
    score: float = Field(default=0.0, ge=0.0)
    source_scores: dict[RetrievalSource, float] = Field(default_factory=dict)
    retrieved_by: list[RetrievalSource] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    graph_distance: int | None = None
    edge_type: EdgeType | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    def add_signal(
        self,
        source: RetrievalSource,
        score: float,
        reason: str,
        *,
        metadata: dict[str, object] | None = None,
    ) -> None:
        """Merge one normalized retrieval signal while preserving provenance."""
        bounded = min(1.0, max(0.0, score))
        self.source_scores[source] = max(self.source_scores.get(source, 0.0), bounded)
        if source not in self.retrieved_by:
            self.retrieved_by.append(source)
        if reason not in self.reasons:
            self.reasons.append(reason)
        if metadata:
            self.metadata.update(metadata)


def merge_candidates(groups: list[list[Candidate]]) -> list[Candidate]:
    """Merge candidates by source-unit identity without losing retrieval evidence."""
    merged: dict[str, Candidate] = {}
    for group in groups:
        for candidate in group:
            existing = merged.get(candidate.unit.unit_id)
            if existing is None:
                merged[candidate.unit.unit_id] = candidate.model_copy(deep=True)
                continue
            for source, score in candidate.source_scores.items():
                existing.add_signal(source, score, "")
            for reason in candidate.reasons:
                if reason and reason not in existing.reasons:
                    existing.reasons.append(reason)
            existing.metadata.update(candidate.metadata)
            if candidate.graph_distance is not None:
                existing.graph_distance = min(
                    existing.graph_distance or candidate.graph_distance,
                    candidate.graph_distance,
                )
            existing.edge_type = existing.edge_type or candidate.edge_type
    return list(merged.values())
