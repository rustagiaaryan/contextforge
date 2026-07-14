"""Bounded knowledge-graph query APIs."""

from __future__ import annotations

import json
import sqlite3
from collections import deque

from contextforge.graph.models import GraphEdge, GraphNeighbor, GraphNode
from contextforge.models import EdgeType, NodeType
from contextforge.storage import Database


class GraphQuery:
    """Read typed nodes, edges, callers, callees, and bounded neighborhoods."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def get_node(self, node_id: str) -> GraphNode | None:
        """Return a graph node by identifier."""
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM graph_nodes WHERE node_id = ?", (node_id,)
            ).fetchone()
        return self._node(row) if row else None

    def edges(self, node_id: str) -> tuple[tuple[GraphEdge, ...], tuple[GraphEdge, ...]]:
        """Return `(incoming, outgoing)` edges for a node."""
        with self.database.connection() as connection:
            incoming = connection.execute(
                "SELECT * FROM graph_edges WHERE target_id = ? ORDER BY source_id", (node_id,)
            ).fetchall()
            outgoing = connection.execute(
                "SELECT * FROM graph_edges WHERE source_id = ? ORDER BY target_id", (node_id,)
            ).fetchall()
        return (
            tuple(self._edge(row) for row in incoming),
            tuple(self._edge(row) for row in outgoing),
        )

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
