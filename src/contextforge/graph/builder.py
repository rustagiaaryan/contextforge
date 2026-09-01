"""Resolve parser hints into a persistent repository knowledge graph."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path, PurePosixPath

import networkx as nx

from contextforge.models import EdgeType, NodeType, SourceUnit
from contextforge.storage import Database


class GraphBuilder:
    """Build a local, typed graph from indexed source units and relation hints."""

    def __init__(self, repository: Path, database: Database) -> None:
        self.repository = repository.resolve(strict=True)
        self.database = database

    def build(self) -> tuple[int, int]:
        """Rebuild graph nodes and resolved edges; return node and edge counts."""
        units = self.database.list_units()
        by_id = {unit.unit_id: unit for unit in units}
        by_name: dict[str, list[SourceUnit]] = defaultdict(list)
        by_qualname: dict[str, list[SourceUnit]] = defaultdict(list)
        for unit in units:
            by_name[unit.name].append(unit)
            by_qualname[unit.qualname].append(unit)

        with self.database.connection() as connection:
            connection.execute("DELETE FROM graph_edges")
            connection.execute("DELETE FROM graph_nodes")
            repository_id = "repository:."
            connection.execute(
                """
                INSERT INTO graph_nodes(node_id, node_type, path, label, unit_id, metadata_json)
                VALUES (?, ?, ?, ?, NULL, ?)
                """,
                (
                    repository_id,
                    NodeType.REPOSITORY.value,
                    ".",
                    self.repository.name,
                    json.dumps({"root_name": self.repository.name}),
                ),
            )
            directories = self._directories(units)
            for directory in directories:
                directory_id = f"directory:{directory}"
                connection.execute(
                    """
                    INSERT INTO graph_nodes(
                        node_id, node_type, path, label, unit_id, metadata_json
                    ) VALUES (?, ?, ?, ?, NULL, '{}')
                    """,
                    (
                        directory_id,
                        NodeType.DIRECTORY.value,
                        directory,
                        PurePosixPath(directory).name,
                    ),
                )
                parent = PurePosixPath(directory).parent.as_posix()
                parent_id = repository_id if parent == "." else f"directory:{parent}"
                self._insert_edge(connection, parent_id, directory_id, EdgeType.CONTAINS, 1.0)
            for unit in units:
                connection.execute(
                    """
                    INSERT INTO graph_nodes(
                        node_id, node_type, path, label, unit_id, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        unit.unit_id,
                        unit.node_type.value,
                        unit.path,
                        unit.qualname,
                        unit.unit_id,
                        json.dumps(
                            {
                                "start_line": unit.start_line,
                                "end_line": unit.end_line,
                                "content_hash": unit.content_hash,
                                "is_test": unit.is_test,
                            }
                        ),
                    ),
                )
                if unit.node_type is NodeType.FILE:
                    parent = PurePosixPath(unit.path).parent.as_posix()
                    parent_id = repository_id if parent == "." else f"directory:{parent}"
                    self._insert_edge(connection, parent_id, unit.unit_id, EdgeType.CONTAINS, 1.0)
                if unit.parent_id and unit.parent_id in by_id:
                    edge_type = (
                        EdgeType.CONTAINS if unit.node_type is NodeType.MODULE else EdgeType.DEFINES
                    )
                    self._insert_edge(connection, unit.parent_id, unit.unit_id, edge_type, 1.0)

            hints = connection.execute(
                "SELECT source_id, edge_type, target, line, confidence FROM relation_hints"
            ).fetchall()
            for hint in hints:
                source_id = str(hint["source_id"])
                target = str(hint["target"])
                edge_type = EdgeType(str(hint["edge_type"]))
                target_id, resolution_confidence = self._resolve_target(
                    source_id,
                    target,
                    edge_type,
                    by_id=by_id,
                    by_name=by_name,
                    by_qualname=by_qualname,
                )
                if target_id and target_id != source_id:
                    self._insert_edge(
                        connection,
                        source_id,
                        target_id,
                        edge_type,
                        float(hint["confidence"]) * resolution_confidence,
                        {"line": hint["line"], "unresolved_target": target},
                    )
            # A resolved reference or call from a test is strong evidence that the test
            # validates the target. Keep the original edge and add an explicit TESTS edge.
            test_links = connection.execute(
                """
                SELECT e.source_id, e.target_id, e.confidence, e.metadata_json
                FROM graph_edges e
                JOIN graph_nodes source ON source.node_id = e.source_id
                JOIN graph_nodes target ON target.node_id = e.target_id
                WHERE source.node_type = ? AND target.node_type != ?
                  AND e.edge_type IN (?, ?)
                """,
                (
                    NodeType.TEST.value,
                    NodeType.TEST.value,
                    EdgeType.CALLS.value,
                    EdgeType.REFERENCES.value,
                ),
            ).fetchall()
            for link in test_links:
                self._insert_edge(
                    connection,
                    str(link["source_id"]),
                    str(link["target_id"]),
                    EdgeType.TESTS,
                    float(link["confidence"]) * 0.9,
                    json.loads(str(link["metadata_json"])),
                )
            self._assign_graph_metrics(connection)
            node_count = int(connection.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0])
            edge_count = int(connection.execute("SELECT COUNT(*) FROM graph_edges").fetchone()[0])
        return node_count, edge_count

    @staticmethod
    def _directories(units: list[SourceUnit]) -> list[str]:
        directories: set[str] = set()
        for unit in units:
            if unit.node_type is not NodeType.FILE:
                continue
            current = PurePosixPath(unit.path).parent
            while current.as_posix() != ".":
                directories.add(current.as_posix())
                current = current.parent
        return sorted(directories, key=lambda path: (path.count("/"), path))

    @staticmethod
    def _resolve_target(
        source_id: str,
        target: str,
        edge_type: EdgeType,
        *,
        by_id: dict[str, SourceUnit],
        by_name: dict[str, list[SourceUnit]],
        by_qualname: dict[str, list[SourceUnit]],
    ) -> tuple[str | None, float]:
        if target in by_id:
            return target, 1.0
        cleaned = target.lstrip(".")
        exact = by_qualname.get(cleaned, [])
        if len(exact) == 1:
            return exact[0].unit_id, 1.0
        source = by_id.get(source_id)
        if source and target.startswith("."):
            package = source.qualname.split(".")[:-1]
            relative = ".".join([*package, cleaned])
            exact = by_qualname.get(relative, [])
            if len(exact) == 1:
                return exact[0].unit_id, 0.9
        final_name = cleaned.rsplit(".", 1)[-1]
        named = by_name.get(final_name, [])
        if len(named) == 1:
            return named[0].unit_id, 0.85
        if source and named:
            same_file = [candidate for candidate in named if candidate.path == source.path]
            if len(same_file) == 1:
                return same_file[0].unit_id, 0.8
        if edge_type is EdgeType.IMPORTS:
            modules = [
                unit
                for qualname, candidates in by_qualname.items()
                if qualname == cleaned or qualname.startswith(f"{cleaned}.")
                for unit in candidates
                if unit.node_type is NodeType.MODULE
            ]
            if len(modules) == 1:
                return modules[0].unit_id, 0.8
        return None, 0.0

    @staticmethod
    def _assign_graph_metrics(connection: sqlite3.Connection) -> None:
        """Persist deterministic weighted communities and dependency centrality."""
        node_rows = connection.execute(
            "SELECT node_id, metadata_json FROM graph_nodes ORDER BY node_id"
        ).fetchall()
        dependency_graph = nx.Graph()
        dependency_graph.add_nodes_from(str(row["node_id"]) for row in node_rows)
        edge_rows = connection.execute(
            """
            SELECT source_id, target_id, confidence
            FROM graph_edges
            WHERE edge_type != ?
            ORDER BY source_id, target_id, edge_type
            """,
            (EdgeType.CONTAINS.value,),
        ).fetchall()
        for row in edge_rows:
            source = str(row["source_id"])
            target = str(row["target_id"])
            if source == target:
                continue
            previous = float(dependency_graph.get_edge_data(source, target, {}).get("weight", 0.0))
            dependency_graph.add_edge(
                source,
                target,
                weight=previous + float(row["confidence"]),
            )
        if dependency_graph.number_of_edges():
            groups = [
                set(group)
                for group in nx.community.greedy_modularity_communities(
                    dependency_graph,
                    weight="weight",
                    resolution=1.0,
                )
            ]
        else:
            groups = [{str(node_id)} for node_id in dependency_graph.nodes]
        groups.sort(key=lambda group: (-len(group), min(group, default="")))
        communities = {
            node_id: community_id
            for community_id, group in enumerate(groups)
            for node_id in sorted(group)
        }
        directed = nx.DiGraph()
        directed.add_nodes_from(str(row["node_id"]) for row in node_rows)
        centrality_edges = connection.execute(
            """
            SELECT source_id, target_id, confidence
            FROM graph_edges
            WHERE edge_type IN (?, ?, ?, ?, ?)
            ORDER BY source_id, target_id, edge_type
            """,
            (
                EdgeType.CALLS.value,
                EdgeType.IMPORTS.value,
                EdgeType.INHERITS.value,
                EdgeType.REFERENCES.value,
                EdgeType.TESTS.value,
            ),
        ).fetchall()
        for row in centrality_edges:
            source = str(row["source_id"])
            target = str(row["target_id"])
            if source == target:
                continue
            previous = float(directed.get_edge_data(source, target, {}).get("weight", 0.0))
            directed.add_edge(source, target, weight=previous + float(row["confidence"]))
        raw_centrality = GraphBuilder._weighted_pagerank(directed)
        maximum = max(raw_centrality.values(), default=1.0)
        centrality = {
            node_id: round(score / maximum, 12) if maximum else 0.0
            for node_id, score in raw_centrality.items()
        }
        for row in node_rows:
            node_id = str(row["node_id"])
            metadata = json.loads(str(row["metadata_json"]))
            metadata["community"] = communities[node_id]
            metadata["centrality"] = centrality[node_id]
            connection.execute(
                "UPDATE graph_nodes SET metadata_json = ? WHERE node_id = ?",
                (json.dumps(metadata, sort_keys=True), node_id),
            )

    @staticmethod
    def _weighted_pagerank(
        graph: nx.DiGraph,
        *,
        damping: float = 0.85,
        tolerance: float = 1e-10,
        max_iterations: int = 100,
    ) -> dict[str, float]:
        """Compute weighted PageRank without requiring NumPy or SciPy."""
        nodes = sorted(str(node_id) for node_id in graph.nodes)
        if not nodes:
            return {}
        node_count = len(nodes)
        ranks = {node_id: 1.0 / node_count for node_id in nodes}
        outgoing: dict[str, tuple[tuple[str, float], ...]] = {}
        totals: dict[str, float] = {}
        for node_id in nodes:
            edges = tuple(
                sorted(
                    (
                        (str(target), float(attributes.get("weight", 1.0)))
                        for _, target, attributes in graph.out_edges(node_id, data=True)
                    ),
                    key=lambda item: item[0],
                )
            )
            outgoing[node_id] = edges
            totals[node_id] = sum(weight for _, weight in edges)
        teleport = (1.0 - damping) / node_count
        for _ in range(max_iterations):
            dangling = sum(ranks[node_id] for node_id in nodes if totals[node_id] == 0.0)
            updated = {node_id: teleport + damping * dangling / node_count for node_id in nodes}
            for source in nodes:
                total = totals[source]
                if total == 0.0:
                    continue
                contribution = damping * ranks[source] / total
                for target, weight in outgoing[source]:
                    updated[target] += contribution * weight
            delta = sum(abs(updated[node_id] - ranks[node_id]) for node_id in nodes)
            ranks = updated
            if delta <= tolerance * node_count:
                break
        return ranks

    @staticmethod
    def _insert_edge(
        connection: sqlite3.Connection,
        source_id: str,
        target_id: str,
        edge_type: EdgeType,
        confidence: float,
        metadata: dict[str, object] | None = None,
    ) -> None:
        connection.execute(
            """
            INSERT OR REPLACE INTO graph_edges(
                source_id, target_id, edge_type, confidence, metadata_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                source_id,
                target_id,
                edge_type.value,
                min(1.0, max(0.0, confidence)),
                json.dumps(metadata or {}),
            ),
        )
