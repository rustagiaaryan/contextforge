from __future__ import annotations

import shutil
from pathlib import Path

from contextforge.graph import GraphBuilder
from contextforge.indexing import RepositoryIndexer
from contextforge.retrieval import (
    Candidate,
    RelatedTestRetriever,
    RetrievalSource,
    StructuralRetriever,
    SymbolRetriever,
)
from contextforge.storage import Database

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"


def _database(tmp_path: Path) -> Database:
    repository = tmp_path / "repository"
    shutil.copytree(FIXTURE, repository)
    database = Database(tmp_path / "index.sqlite3")
    RepositoryIndexer(repository, database).index()
    GraphBuilder(repository, database).build()
    return database


def test_structural_expansion_is_anchored_bounded_and_distance_penalized(tmp_path: Path) -> None:
    database = _database(tmp_path)
    anchor = SymbolRetriever(database).search("Mount.resolve", limit=1)

    results = StructuralRetriever(database).expand(anchor, max_depth=2, max_nodes=5)

    assert len(results) <= 5
    join_path = next(result for result in results if result.unit.name == "join_path")
    assert join_path.graph_distance == 1
    assert RetrievalSource.CALL_GRAPH in join_path.retrieved_by
    assert join_path.metadata["anchor_id"] == anchor[0].unit.unit_id
    assert all(result.unit.unit_id != anchor[0].unit.unit_id for result in results)


def test_related_test_discovery_connects_validation_to_implementation(tmp_path: Path) -> None:
    database = _database(tmp_path)
    production: list[Candidate] = SymbolRetriever(database).search("dispatch", limit=1)

    tests = RelatedTestRetriever(database).find(
        [candidate.unit for candidate in production],
        task="mounted route prefix is lost",
    )

    assert tests
    assert tests[0].unit.qualname.endswith("test_mounted_prefix_is_preserved")
    assert RetrievalSource.RELATED_TESTS in tests[0].retrieved_by
    assert "graph" in tests[0].reasons[0] or "call" in tests[0].reasons[0]
