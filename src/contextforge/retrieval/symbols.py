"""Exact and fuzzy repository symbol retrieval."""

from __future__ import annotations

from difflib import SequenceMatcher

from contextforge.models import NodeType
from contextforge.retrieval.models import Candidate, RetrievalSource
from contextforge.retrieval.text import query_terms
from contextforge.storage import Database

SYMBOL_TYPES = (NodeType.CLASS, NodeType.FUNCTION, NodeType.METHOD, NodeType.TEST)


class SymbolRetriever:
    """Rank exact, suffix, substring, and fuzzy symbol-name matches."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def search(self, query: str, *, limit: int = 20) -> list[Candidate]:
        """Search symbols without requiring FTS syntax or exact casing."""
        if limit < 1:
            return []
        lowered = query.strip().lower()
        terms = query_terms(query)
        if not terms:
            return []
        candidates: list[Candidate] = []
        for unit in self.database.list_units(node_types=SYMBOL_TYPES):
            name = unit.name.lower()
            qualname = unit.qualname.lower()
            score = self._score(lowered, terms, name, qualname)
            if score < 0.35:
                continue
            exact = any(term == name or qualname.endswith(f".{term}") for term in terms)
            reason = (
                f"Exact symbol match for {unit.qualname}."
                if exact
                else f"Fuzzy symbol match for {unit.qualname}."
            )
            candidate = Candidate(unit=unit)
            candidate.add_signal(
                RetrievalSource.SYMBOL,
                score,
                reason,
                metadata={"exact_symbol_match": exact},
            )
            candidates.append(candidate)
        candidates.sort(
            key=lambda candidate: (
                -candidate.source_scores[RetrievalSource.SYMBOL],
                candidate.unit.path,
                candidate.unit.start_line,
            )
        )
        return candidates[:limit]

    @staticmethod
    def _score(query: str, terms: tuple[str, ...], name: str, qualname: str) -> float:
        if query in (qualname, name) or qualname.endswith(f".{query}"):
            return 1.0
        score = 0.0
        for term in terms:
            if term == name:
                score = max(score, 0.98)
            elif qualname.endswith(f".{term}"):
                score = max(score, 0.94)
            elif term in name:
                score = max(score, 0.82)
            elif term in qualname:
                score = max(score, 0.68)
            else:
                score = max(score, SequenceMatcher(None, term, name).ratio() * 0.72)
        return score
