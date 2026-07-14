"""One-pass bounded query evolution from initial repository evidence."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from contextforge.graph import GraphQuery
from contextforge.models import EdgeType
from contextforge.retrieval.models import Candidate
from contextforge.retrieval.text import query_terms
from contextforge.storage import Database


class QueryEvolutionTrace(BaseModel):
    """Trace of concepts derived for the single allowed second retrieval pass."""

    model_config = ConfigDict(frozen=True)

    original_terms: tuple[str, ...]
    derived_concepts: tuple[str, ...]
    evolved_query: str
    anchors_examined: int = Field(ge=0)
    added_candidate_count: int = Field(default=0, ge=0)


class QueryEvolution:
    """Derive a finite concept set from symbols, APIs, and graph relationships."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.graph = GraphQuery(database)

    def evolve(
        self,
        task: str,
        candidates: list[Candidate],
        *,
        max_anchors: int = 6,
        max_concepts: int = 12,
    ) -> QueryEvolutionTrace:
        """Produce one expanded query; this method never recursively searches."""
        original = query_terms(task)
        original_set = set(original)
        concepts: list[str] = []
        seen = set(original)

        def add(values: tuple[str, ...]) -> None:
            for value in values:
                if value in seen or len(value) < 3:
                    continue
                seen.add(value)
                concepts.append(value)
                if len(concepts) >= max_concepts:
                    return

        anchors = sorted(candidates, key=lambda candidate: -candidate.score)[:max_anchors]
        for candidate in anchors:
            add(query_terms(candidate.unit.name, limit=3))
            add(query_terms(candidate.unit.signature, limit=5))
            add(query_terms(candidate.unit.docstring, limit=5))
            if len(concepts) >= max_concepts:
                break
            neighbors = self.graph.neighbors(
                candidate.unit.unit_id,
                edge_types={EdgeType.CALLS, EdgeType.IMPORTS, EdgeType.INHERITS},
                max_depth=1,
                limit=8,
            )
            for neighbor in neighbors:
                add(query_terms(neighbor.node.label.rsplit(".", 1)[-1], limit=3))
                if len(concepts) >= max_concepts:
                    break
        derived = tuple(concept for concept in concepts if concept not in original_set)[
            :max_concepts
        ]
        suffix = " ".join(derived)
        evolved = f"{task.rstrip()}\nRelated repository concepts: {suffix}" if suffix else task
        return QueryEvolutionTrace(
            original_terms=original,
            derived_concepts=derived,
            evolved_query=evolved,
            anchors_examined=len(anchors),
        )
