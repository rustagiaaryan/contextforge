from __future__ import annotations

import shutil
from pathlib import Path

from contextforge.indexing import RepositoryIndexer
from contextforge.retrieval import LexicalRetriever, RetrievalSource, SymbolRetriever
from contextforge.storage import Database

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"


def _database(tmp_path: Path) -> Database:
    repository = tmp_path / "repository"
    shutil.copytree(FIXTURE, repository)
    database = Database(tmp_path / "index.sqlite3")
    RepositoryIndexer(repository, database).index()
    return database


def test_bm25_search_ranks_routing_evidence_with_provenance(tmp_path: Path) -> None:
    results = LexicalRetriever(_database(tmp_path)).search(
        "mounted applications lose their route prefix"
    )

    assert results
    assert results[0].unit.path == "app/routing.py"
    assert RetrievalSource.LEXICAL in results[0].retrieved_by
    assert results[0].source_scores[RetrievalSource.LEXICAL] == 1.0
    assert "prefix" in results[0].metadata["matched_terms"]


def test_symbol_search_supports_exact_and_fuzzy_names(tmp_path: Path) -> None:
    retriever = SymbolRetriever(_database(tmp_path))

    exact = retriever.search("Mount.resolve")
    fuzzy = retriever.search("dispach")

    assert exact[0].unit.qualname == "app.routing.Mount.resolve"
    assert exact[0].metadata["exact_symbol_match"] is True
    assert fuzzy[0].unit.name == "dispatch"
    assert RetrievalSource.SYMBOL in fuzzy[0].retrieved_by
