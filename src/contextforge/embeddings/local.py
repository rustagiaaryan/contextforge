"""Deterministic, zero-download feature-hashing embeddings."""

from __future__ import annotations

import math
import re
from hashlib import blake2b
from itertools import pairwise

TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+|[^\w\s]")


class LocalHashEmbeddingProvider:
    """Map code tokens and character n-grams into a normalized signed hash vector.

    This is a deterministic local semantic baseline, not a trained neural model. It
    preserves identifier/subword overlap and makes caching and hybrid retrieval fully
    functional without a model download or API key.
    """

    name = "local-hash-v1"

    def __init__(self, dimensions: int = 384) -> None:
        if dimensions < 32:
            raise ValueError("Embedding dimensions must be at least 32")
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed text batches deterministically with L2 normalization."""
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = [token.lower() for token in TOKEN.findall(text)]
        features: list[tuple[str, float]] = [(f"tok:{token}", 1.0) for token in tokens]
        for token in tokens:
            padded = f"^{token}$"
            features.extend(
                (f"tri:{padded[index : index + 3]}", 0.45)
                for index in range(max(0, len(padded) - 2))
            )
        features.extend((f"pair:{left}:{right}", 0.65) for left, right in pairwise(tokens))
        for feature, weight in features:
            digest = blake2b(feature.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "little")
            index = value % self.dimensions
            sign = 1.0 if value & (1 << 63) else -1.0
            vector[index] += sign * weight
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            return [value / norm for value in vector]
        return vector
