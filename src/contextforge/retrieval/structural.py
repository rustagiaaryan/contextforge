"""Lexically anchored, bounded structural retrieval."""

from __future__ import annotations

from contextforge.graph import GraphQuery
from contextforge.models import EdgeType
from contextforge.retrieval.models import Candidate, RetrievalSource, merge_candidates
from contextforge.storage import Database

DEFAULT_STRUCTURAL_EDGES = {
    EdgeType.CALLS,
    EdgeType.IMPORTS,
    EdgeType.INHERITS,
    EdgeType.DEFINES,
    EdgeType.REFERENCES,
    EdgeType.TESTS,
}

EDGE_WEIGHT = {
    EdgeType.CALLS: 1.0,
    EdgeType.TESTS: 1.0,
    EdgeType.IMPORTS: 0.82,
    EdgeType.INHERITS: 0.88,
    EdgeType.DEFINES: 0.76,
    EdgeType.REFERENCES: 0.68,
    EdgeType.CONTAINS: 0.55,
    EdgeType.CHANGED_IN: 0.5,
    EdgeType.CO_CHANGED_WITH: 0.55,
}


def _source(edge_type: EdgeType) -> RetrievalSource:
    if edge_type is EdgeType.CALLS:
        return RetrievalSource.CALL_GRAPH
    if edge_type is EdgeType.IMPORTS:
        return RetrievalSource.IMPORT_GRAPH
    if edge_type is EdgeType.INHERITS:
        return RetrievalSource.INHERITANCE_GRAPH
    if edge_type is EdgeType.TESTS:
        return RetrievalSource.RELATED_TESTS
    return RetrievalSource.GRAPH


class StructuralRetriever:
    """Expand only around supplied search anchors with strict traversal bounds."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.graph = GraphQuery(database)

    def expand(
        self,
        anchors: list[Candidate],
        *,
        edge_types: set[EdgeType] | None = None,
        max_depth: int = 2,
        max_nodes: int = 40,
        anchors_limit: int = 8,
    ) -> list[Candidate]:
        """Return source-backed neighbors scored by anchor, distance, edge, and confidence."""
        if max_depth < 1 or max_nodes < 1:
            return []
        ordered = sorted(
            anchors,
            key=lambda candidate: (
                -max(candidate.source_scores.values(), default=candidate.score),
                candidate.unit.unit_id,
            ),
        )[:anchors_limit]
        groups: list[list[Candidate]] = []
        remaining = max_nodes
        for anchor in ordered:
            if remaining <= 0:
                break
            anchor_score = max(anchor.source_scores.values(), default=max(anchor.score, 0.1))
            candidates: list[Candidate] = []
            neighbors = self.graph.neighbors(
                anchor.unit.unit_id,
                edge_types=edge_types or DEFAULT_STRUCTURAL_EDGES,
                max_depth=max_depth,
                limit=remaining,
            )
            for neighbor in neighbors:
                if not neighbor.node.unit_id:
                    continue
                unit = self.database.get_unit(neighbor.node.unit_id)
                if unit is None:
                    continue
                distance_penalty = 0.72**neighbor.distance
                score = (
                    anchor_score
                    * distance_penalty
                    * neighbor.confidence
                    * EDGE_WEIGHT[neighbor.via_edge]
                )
                source = _source(neighbor.via_edge)
                candidate = Candidate(
                    unit=unit,
                    graph_distance=neighbor.distance,
                    edge_type=neighbor.via_edge,
                )
                candidate.add_signal(
                    source,
                    score,
                    f"{neighbor.via_edge.value} {neighbor.direction} at graph distance "
                    f"{neighbor.distance} from {anchor.unit.qualname}.",
                    metadata={
                        "anchor_id": anchor.unit.unit_id,
                        "graph_confidence": neighbor.confidence,
                    },
                )
                candidates.append(candidate)
            groups.append(candidates)
            remaining -= len(neighbors)
        merged = merge_candidates(groups)
        merged.sort(
            key=lambda candidate: (
                -max(candidate.source_scores.values(), default=0.0),
                candidate.unit.path,
                candidate.unit.start_line,
            )
        )
        return merged[:max_nodes]
