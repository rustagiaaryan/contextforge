"""Reranker extension protocol."""

from typing import Protocol

from contextforge.retrieval.models import Candidate
from contextforge.routing import RetrievalRoute


class Reranker(Protocol):
    """Interface for deterministic or learned candidate rerankers."""

    def rerank(
        self, candidates: list[Candidate], *, task: str, route: RetrievalRoute
    ) -> list[Candidate]:
        """Return candidates ordered by descending unified relevance."""
