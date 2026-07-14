"""Embedding provider protocol."""

from typing import Protocol


class EmbeddingProvider(Protocol):
    """Provider contract for local or externally hosted embedding models."""

    name: str
    dimensions: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch in input order or raise a provider-specific exception."""
