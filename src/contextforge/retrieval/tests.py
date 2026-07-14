"""Multi-signal related-test discovery."""

from __future__ import annotations

from pathlib import PurePosixPath

from contextforge.graph import GraphQuery
from contextforge.models import EdgeType, NodeType, SourceUnit
from contextforge.retrieval.models import Candidate, RetrievalSource
from contextforge.retrieval.text import query_terms
from contextforge.storage import Database


class RelatedTestRetriever:
    """Find tests using graph links, naming, paths, and lexical task overlap."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.graph = GraphQuery(database)

    def find(
        self,
        anchors: list[SourceUnit],
        *,
        task: str = "",
        limit: int = 12,
    ) -> list[Candidate]:
        """Return likely validation symbols for implementation anchors."""
        if not anchors or limit < 1:
            return []
        anchor_ids = {anchor.unit_id for anchor in anchors}
        anchor_paths = {anchor.path for anchor in anchors}
        anchor_names = {
            name.lower()
            for anchor in anchors
            for name in (anchor.name, PurePosixPath(anchor.path).stem)
            if len(name) > 2
        }
        task_terms = set(query_terms(task))
        results: list[Candidate] = []
        for unit in self.database.list_units(node_types=(NodeType.TEST,)):
            score = 0.0
            signals: list[str] = []
            incoming, outgoing = self.graph.edges(unit.unit_id)
            direct = [
                edge
                for edge in (*incoming, *outgoing)
                if (edge.source_id in anchor_ids or edge.target_id in anchor_ids)
                and edge.edge_type in {EdgeType.CALLS, EdgeType.REFERENCES, EdgeType.TESTS}
            ]
            if direct:
                score += 0.72
                signals.append("direct call/reference edge")
            neighbors = self.graph.neighbors(
                unit.unit_id,
                edge_types={
                    EdgeType.CALLS,
                    EdgeType.REFERENCES,
                    EdgeType.IMPORTS,
                    EdgeType.DEFINES,
                    EdgeType.TESTS,
                },
                max_depth=3,
                limit=40,
            )
            structurally_related = any(
                neighbor.node.node_id in anchor_ids or neighbor.node.path in anchor_paths
                for neighbor in neighbors
            )
            if structurally_related:
                score += 0.48
                signals.append("bounded graph path to anchor")
            lower_name = unit.qualname.lower()
            name_matches = sorted(name for name in anchor_names if name in lower_name)
            if name_matches:
                score += min(0.3, 0.15 * len(name_matches))
                signals.append(f"test name matches {', '.join(name_matches)}")
            searchable = f"{unit.qualname} {unit.docstring} {unit.content}".lower()
            overlap = sorted(term for term in task_terms if term in searchable)
            if overlap:
                score += min(0.2, len(overlap) * 0.04)
                signals.append(f"task overlap {', '.join(overlap[:4])}")
            if score <= 0.0:
                continue
            candidate = Candidate(unit=unit)
            candidate.add_signal(
                RetrievalSource.RELATED_TESTS,
                min(1.0, score),
                "Related test: " + "; ".join(signals) + ".",
                metadata={"test_signals": signals},
            )
            results.append(candidate)
        results.sort(
            key=lambda candidate: (
                -candidate.source_scores[RetrievalSource.RELATED_TESTS],
                candidate.unit.path,
                candidate.unit.start_line,
            )
        )
        return results[:limit]
