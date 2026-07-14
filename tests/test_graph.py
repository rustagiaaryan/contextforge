from __future__ import annotations

import shutil
from pathlib import Path

from contextforge.graph import GraphBuilder, GraphQuery
from contextforge.indexing import RepositoryIndexer
from contextforge.models import EdgeType, NodeType
from contextforge.storage import Database

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"


def _graph(tmp_path: Path) -> tuple[Database, GraphQuery]:
    repository = tmp_path / "repository"
    shutil.copytree(FIXTURE, repository)
    database = Database(tmp_path / "index.sqlite3")
    RepositoryIndexer(repository, database).index()
    GraphBuilder(repository, database).build()
    return database, GraphQuery(database)


def test_graph_builds_containment_import_and_call_edges(tmp_path: Path) -> None:
    database, graph = _graph(tmp_path)
    resolve = next(
        unit for unit in database.list_units() if unit.qualname.endswith("Mount.resolve")
    )
    join_path = next(unit for unit in database.list_units() if unit.name == "join_path")
    dispatch = next(unit for unit in database.list_units() if unit.name == "dispatch")

    assert [node.node_id for node in graph.callees(resolve.unit_id)] == [join_path.unit_id]
    assert [node.node_id for node in graph.callers(resolve.unit_id)] == [dispatch.unit_id]

    incoming, outgoing = graph.edges(resolve.unit_id)
    assert any(edge.edge_type is EdgeType.DEFINES for edge in incoming)
    assert any(edge.edge_type is EdgeType.CALLS for edge in outgoing)


def test_graph_contains_required_node_types_and_bounded_expansion(tmp_path: Path) -> None:
    database, graph = _graph(tmp_path)
    resolve = next(
        unit for unit in database.list_units() if unit.qualname.endswith("Mount.resolve")
    )
    neighbors = graph.neighbors(
        resolve.unit_id,
        edge_types={EdgeType.CALLS, EdgeType.DEFINES},
        max_depth=2,
        limit=3,
    )

    assert len(neighbors) <= 3
    assert any(neighbor.node.node_type is NodeType.CLASS for neighbor in neighbors)
    assert any(neighbor.node.label.endswith("join_path") for neighbor in neighbors)
    assert all(1 <= neighbor.distance <= 2 for neighbor in neighbors)
