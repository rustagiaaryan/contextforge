"""Bounded knowledge-graph query APIs."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict, deque

from contextforge.graph.models import GraphEdge, GraphNeighbor, GraphNode
from contextforge.models import EdgeType, NodeType
from contextforge.storage import Database


class GraphQuery:
    """Read typed nodes, edges, callers, callees, and bounded neighborhoods."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self._nodes: dict[str, GraphNode] | None = None
        self._incoming: dict[str, tuple[GraphEdge, ...]] | None = None
        self._outgoing: dict[str, tuple[GraphEdge, ...]] | None = None

    def get_node(self, node_id: str) -> GraphNode | None:
        """Return a graph node by identifier."""
        self._load_cache()
        assert self._nodes is not None
        return self._nodes.get(node_id)

    def edges(self, node_id: str) -> tuple[tuple[GraphEdge, ...], tuple[GraphEdge, ...]]:
        """Return `(incoming, outgoing)` edges for a node."""
        self._load_cache()
        assert self._incoming is not None and self._outgoing is not None
        return self._incoming.get(node_id, ()), self._outgoing.get(node_id, ())

    def callers(self, node_id: str) -> tuple[GraphNode, ...]:
        """Return local symbols with resolved `CALLS` edges into a node."""
        return self._linked_nodes(node_id, EdgeType.CALLS, incoming=True)

    def callees(self, node_id: str) -> tuple[GraphNode, ...]:
        """Return local symbols called by a node."""
        return self._linked_nodes(node_id, EdgeType.CALLS, incoming=False)

    def neighbors(
        self,
        node_id: str,
        *,
        edge_types: set[EdgeType] | None = None,
        max_depth: int = 1,
        limit: int = 40,
    ) -> tuple[GraphNeighbor, ...]:
        """Expand both directions with strict depth/node limits and path confidence."""
        if max_depth < 1 or limit < 1:
            return ()
        allowed = edge_types or set(EdgeType)
        queue: deque[tuple[str, int, float]] = deque([(node_id, 0, 1.0)])
        visited = {node_id}
        results: list[GraphNeighbor] = []
        while queue and len(results) < limit:
            current, distance, path_confidence = queue.popleft()
            if distance >= max_depth:
                continue
            incoming, outgoing = self.edges(current)
            traversals = [
                (edge.source_id, edge, "incoming") for edge in incoming if edge.edge_type in allowed
            ] + [
                (edge.target_id, edge, "outgoing") for edge in outgoing if edge.edge_type in allowed
            ]
            traversals.sort(key=lambda item: (-item[1].confidence, item[0], item[2]))
            for target_id, edge, direction in traversals:
                if target_id in visited:
                    continue
                node = self.get_node(target_id)
                if node is None:
                    continue
                visited.add(target_id)
                confidence = path_confidence * edge.confidence
                next_distance = distance + 1
                results.append(
                    GraphNeighbor(
                        node=node,
                        distance=next_distance,
                        via_edge=edge.edge_type,
                        direction=direction,
                        confidence=confidence,
                    )
                )
                if len(results) >= limit:
                    break
                queue.append((target_id, next_distance, confidence))
        return tuple(results)

    def _linked_nodes(
        self, node_id: str, edge_type: EdgeType, *, incoming: bool
    ) -> tuple[GraphNode, ...]:
        edge_column = "target_id" if incoming else "source_id"
        linked_column = "source_id" if incoming else "target_id"
        query = f"""
            SELECT n.* FROM graph_edges e
            JOIN graph_nodes n ON n.node_id = e.{linked_column}
            WHERE e.{edge_column} = ? AND e.edge_type = ?
            ORDER BY e.confidence DESC, n.node_id
        """
        with self.database.connection() as connection:
            rows = connection.execute(query, (node_id, edge_type.value)).fetchall()
        return tuple(self._node(row) for row in rows)

    def _load_cache(self) -> None:
        if self._nodes is not None:
            return
        with self.database.connection() as connection:
            node_rows = connection.execute("SELECT * FROM graph_nodes").fetchall()
            edge_rows = connection.execute("SELECT * FROM graph_edges").fetchall()
        nodes = {str(row["node_id"]): self._node(row) for row in node_rows}
        incoming: dict[str, list[GraphEdge]] = defaultdict(list)
        outgoing: dict[str, list[GraphEdge]] = defaultdict(list)
        for row in edge_rows:
            edge = self._edge(row)
            incoming[edge.target_id].append(edge)
            outgoing[edge.source_id].append(edge)
        self._nodes = nodes
        self._incoming = {
            node_id: tuple(sorted(edges, key=lambda edge: (-edge.confidence, edge.source_id)))
            for node_id, edges in incoming.items()
        }
        self._outgoing = {
            node_id: tuple(sorted(edges, key=lambda edge: (-edge.confidence, edge.target_id)))
            for node_id, edges in outgoing.items()
        }

    @staticmethod
    def _node(row: sqlite3.Row) -> GraphNode:
        values = dict(row)
        return GraphNode(
            node_id=str(values["node_id"]),
            node_type=NodeType(str(values["node_type"])),
            path=str(values["path"]) if values["path"] is not None else None,
            label=str(values["label"]),
            unit_id=str(values["unit_id"]) if values["unit_id"] is not None else None,
            metadata=json.loads(str(values["metadata_json"])),
        )

    @staticmethod
    def _edge(row: sqlite3.Row) -> GraphEdge:
        values = dict(row)
        return GraphEdge(
            source_id=str(values["source_id"]),
            target_id=str(values["target_id"]),
            edge_type=EdgeType(str(values["edge_type"])),
            confidence=float(values["confidence"]),
            metadata=json.loads(str(values["metadata_json"])),
        )
