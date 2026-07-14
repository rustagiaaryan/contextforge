"""Cached batched embedding indexing and cosine retrieval."""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass

from contextforge.embeddings import EmbeddingProvider
from contextforge.models import NodeType, SourceUnit
from contextforge.retrieval.models import Candidate, RetrievalSource
from contextforge.storage import Database

SEMANTIC_TYPES = (
    NodeType.FILE,
    NodeType.CLASS,
    NodeType.FUNCTION,
    NodeType.METHOD,
    NodeType.TEST,
)


@dataclass(frozen=True)
class SemanticIndexStats:
    """Embedding cache update result."""

    embedded_units: int
    cached_units: int
    enabled: bool
    error: str | None = None


def _embedding_text(unit: SourceUnit) -> str:
    return "\n".join(
        part
        for part in (unit.path, unit.qualname, unit.signature, unit.docstring, unit.content)
        if part
    )


def _pack(vector: list[float]) -> bytes:
    return struct.pack(f"<{len(vector)}f", *vector)


def _unpack(data: bytes, dimensions: int) -> tuple[float, ...]:
    return struct.unpack(f"<{dimensions}f", data)


class SemanticIndexer:
    """Generate only missing or content-invalidated embeddings in batches."""

    def __init__(
        self,
        database: Database,
        provider: EmbeddingProvider,
        *,
        batch_size: int = 64,
    ) -> None:
        self.database = database
        self.provider = provider
        self.batch_size = max(1, batch_size)

    def index(self) -> SemanticIndexStats:
        """Update the persistent embedding cache, degrading cleanly on failure."""
        units = self.database.list_units(node_types=SEMANTIC_TYPES)
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT unit_id, content_hash FROM embeddings WHERE provider = ?",
                (self.provider.name,),
            ).fetchall()
        cached = {str(row["unit_id"]): str(row["content_hash"]) for row in rows}
        pending = [unit for unit in units if cached.get(unit.unit_id) != unit.content_hash]
        try:
            for offset in range(0, len(pending), self.batch_size):
                batch = pending[offset : offset + self.batch_size]
                vectors = self.provider.embed([_embedding_text(unit) for unit in batch])
                if len(vectors) != len(batch):
                    raise ValueError("Embedding provider returned the wrong batch length")
                with self.database.connection() as connection:
                    for unit, vector in zip(batch, vectors, strict=True):
                        if len(vector) != self.provider.dimensions:
                            raise ValueError("Embedding provider returned wrong dimensions")
                        connection.execute(
                            """
                            INSERT OR REPLACE INTO embeddings(
                                unit_id, provider, content_hash, dimensions, vector
                            ) VALUES (?, ?, ?, ?, ?)
                            """,
                            (
                                unit.unit_id,
                                self.provider.name,
                                unit.content_hash,
                                self.provider.dimensions,
                                _pack(vector),
                            ),
                        )
        except Exception as error:  # provider failures must not disable lexical retrieval
            return SemanticIndexStats(
                embedded_units=0,
                cached_units=len(units) - len(pending),
                enabled=False,
                error=f"{type(error).__name__}: {error}",
            )
        return SemanticIndexStats(
            embedded_units=len(pending),
            cached_units=len(units) - len(pending),
            enabled=True,
        )


class SemanticRetriever:
    """Rank cached source-unit embeddings by cosine similarity."""

    def __init__(self, database: Database, provider: EmbeddingProvider) -> None:
        self.database = database
        self.provider = provider
        self.last_error: str | None = None

    def search(self, query: str, *, limit: int = 30) -> list[Candidate]:
        """Return semantic candidates or an empty list when the provider is unavailable."""
        if not query.strip() or limit < 1:
            return []
        try:
            vectors = self.provider.embed([query])
            if len(vectors) != 1 or len(vectors[0]) != self.provider.dimensions:
                raise ValueError("Embedding provider returned an invalid query vector")
            query_vector = vectors[0]
        except Exception as error:
            self.last_error = f"{type(error).__name__}: {error}"
            return []
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT u.*, e.dimensions, e.vector
                FROM embeddings e JOIN units u ON u.unit_id = e.unit_id
                WHERE e.provider = ? AND e.content_hash = u.content_hash
                """,
                (self.provider.name,),
            ).fetchall()
        scored: list[tuple[float, SourceUnit]] = []
        query_norm = math.sqrt(sum(value * value for value in query_vector)) or 1.0
        for row in rows:
            vector = _unpack(bytes(row["vector"]), int(row["dimensions"]))
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            cosine = sum(left * right for left, right in zip(query_vector, vector, strict=True)) / (
                query_norm * norm
            )
            scored.append((max(0.0, cosine), Database._row_to_unit(row)))
        scored.sort(key=lambda item: (-item[0], item[1].path, item[1].start_line))
        results: list[Candidate] = []
        for similarity, unit in scored[:limit]:
            if similarity <= 0.0:
                continue
            candidate = Candidate(unit=unit)
            candidate.add_signal(
                RetrievalSource.SEMANTIC,
                similarity,
                f"Local embedding similarity {similarity:.3f} to the task.",
                metadata={"semantic_similarity": similarity, "provider": self.provider.name},
            )
            results.append(candidate)
        return results
