"""Pluggable embedding providers."""

from contextforge.embeddings.base import EmbeddingProvider
from contextforge.embeddings.local import LocalHashEmbeddingProvider

__all__ = ["EmbeddingProvider", "LocalHashEmbeddingProvider"]
