from __future__ import annotations

import shutil
from pathlib import Path

from contextforge.embeddings import LocalHashEmbeddingProvider
from contextforge.indexing import RepositoryIndexer
from contextforge.retrieval import RetrievalSource, SemanticIndexer, SemanticRetriever
from contextforge.storage import Database

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"


class FailingProvider:
    name = "failing"
    dimensions = 32

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("model unavailable")


def _database(tmp_path: Path) -> Database:
    repository = tmp_path / "repository"
    shutil.copytree(FIXTURE, repository)
    database = Database(tmp_path / "index.sqlite3")
    RepositoryIndexer(repository, database).index()
    return database


def test_semantic_embeddings_are_batched_cached_and_searchable(tmp_path: Path) -> None:
    database = _database(tmp_path)
    provider = LocalHashEmbeddingProvider(64)
    indexer = SemanticIndexer(database, provider, batch_size=3)

    first = indexer.index()
    second = indexer.index()
    results = SemanticRetriever(database, provider).search("preserve mounted URL prefix")

    assert first.enabled and first.embedded_units > 0
    assert second.enabled and second.embedded_units == 0
    assert second.cached_units == first.embedded_units
    assert results
    assert any(result.unit.path == "app/routing.py" for result in results[:5])
    assert RetrievalSource.SEMANTIC in results[0].retrieved_by


def test_semantic_provider_failure_degrades_to_empty_results(tmp_path: Path) -> None:
    database = _database(tmp_path)
    provider = FailingProvider()

    status = SemanticIndexer(database, provider).index()
    retriever = SemanticRetriever(database, provider)

    assert not status.enabled
    assert "model unavailable" in (status.error or "")
    assert retriever.search("route prefix") == []
    assert "model unavailable" in (retriever.last_error or "")
