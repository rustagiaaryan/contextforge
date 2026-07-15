"""Graph-native query, path, and explain operations over portable artifacts."""

from __future__ import annotations

import json
from collections import deque
from itertools import pairwise
from pathlib import Path
from typing import Any

import networkx as nx
from rapidfuzz import fuzz, process

from contextforge.codegraph.models import CodeGraph


def load_graph(path: Path) -> CodeGraph:
    """Load and validate a ContextForge graph JSON artifact."""
    resolved = path.expanduser().resolve(strict=True)
    if resolved.suffix.lower() != ".json":
        raise ValueError("Graph artifact must be a JSON file")
    if resolved.stat().st_size > 100_000_000:
        raise ValueError("Graph artifact exceeds the 100 MB safety limit")
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("Unsupported ContextForge graph schema")
    nodes = payload.get("nodes")
    edges = payload.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError("Graph artifact needs node and edge lists")
    graph: CodeGraph = nx.MultiDiGraph()
    for record in nodes:
        if not isinstance(record, dict) or not isinstance(record.get("id"), str):
            raise ValueError("Invalid graph node record")
        node = dict(record)
        node_id = node.pop("id")
        graph.add_node(node_id, id=node_id, **node)
    for record in edges:
        if not isinstance(record, dict):
            raise ValueError("Invalid graph edge record")
        source = record.get("source")
        target = record.get("target")
        if not isinstance(source, str) or not isinstance(target, str):
            raise ValueError("Graph edge needs string endpoints")
        if source not in graph or target not in graph:
            raise ValueError("Graph edge references an unknown node")
        edge = dict(record)
        edge.pop("source", None)
        edge.pop("target", None)
        key = str(edge.pop("key", f"edge:{graph.number_of_edges()}"))
        graph.add_edge(source, target, key=key, **edge)
    metadata = payload.get("metadata", {})
    if isinstance(metadata, dict):
        graph.graph.update(metadata)
    return graph


def query_graph(
    graph: CodeGraph,
    question: str,
    *,
    limit: int = 25,
    hops: int = 1,
) -> dict[str, Any]:
    """Return a question-scoped subgraph using fuzzy anchors plus bounded traversal."""
    query = question.strip()
    if not query:
        raise ValueError("Graph query cannot be empty")
    if limit < 1 or limit > 200 or hops < 0 or hops > 3:
        raise ValueError("Graph query bounds are limit 1..200 and hops 0..3")
    ranked = sorted(
        (
            (_query_score(query, attributes), str(node_id))
            for node_id, attributes in graph.nodes(data=True)
        ),
        key=lambda item: (-item[0], item[1]),
    )
    anchors = [node_id for score, node_id in ranked[:3] if score >= 20.0]
    if not anchors and ranked:
        anchors = [ranked[0][1]]
    selected: list[str] = []
    visited: set[str] = set()
    queue: deque[tuple[str, int]] = deque((anchor, 0) for anchor in anchors)
    while queue and len(selected) < limit:
        node_id, distance = queue.popleft()
        if node_id in visited:
            continue
        visited.add(node_id)
        selected.append(node_id)
        if distance >= hops:
            continue
        neighbors = sorted(
            {str(node) for node in graph.predecessors(node_id)}
            | {str(node) for node in graph.successors(node_id)},
            key=lambda candidate: (-int(graph.degree(candidate)), candidate),
        )
        queue.extend((neighbor, distance + 1) for neighbor in neighbors if neighbor not in visited)
    selected_set = set(selected)
    nodes = [{"id": node_id, **dict(graph.nodes[node_id])} for node_id in selected]
    edges = []
    for source, target, key, attributes in graph.edges(data=True, keys=True):
        if str(source) in selected_set and str(target) in selected_set:
            edges.append(
                {"source": str(source), "target": str(target), "key": str(key), **dict(attributes)}
            )
    return {
        "question": query,
        "anchors": [
            {
                "id": node_id,
                "label": str(graph.nodes[node_id].get("label", node_id)),
                "score": next(score for score, candidate in ranked if candidate == node_id),
            }
            for node_id in anchors
        ],
        "nodes": nodes,
        "edges": edges,
    }


def shortest_path(graph: CodeGraph, source: str, target: str) -> dict[str, Any]:
    """Resolve two fuzzy node labels and return their strongest shortest path."""
    source_id = resolve_node(graph, source)
    target_id = resolve_node(graph, target)
    undirected = graph.to_undirected()
    try:
        node_path = nx.shortest_path(undirected, source_id, target_id)
    except nx.NetworkXNoPath as error:
        raise ValueError(f"No graph path between {source!r} and {target!r}") from error
    steps = []
    for left, right in pairwise(node_path):
        candidates: list[dict[str, Any]] = []
        candidates.extend(graph.get_edge_data(left, right, default={}).values())
        candidates.extend(graph.get_edge_data(right, left, default={}).values())
        edge = max(candidates, key=lambda item: float(item.get("weight", 0.0)))
        forward = bool(graph.get_edge_data(left, right))
        steps.append(
            {
                "source": str(graph.nodes[left].get("label", left)),
                "target": str(graph.nodes[right].get("label", right)),
                "relation": str(edge.get("relation", "related")),
                "confidence": str(edge.get("confidence", "INFERRED")),
                "direction": "outgoing" if forward else "incoming",
            }
        )
    return {
        "source": {"id": source_id, "label": graph.nodes[source_id].get("label", source_id)},
        "target": {"id": target_id, "label": graph.nodes[target_id].get("label", target_id)},
        "hops": len(steps),
        "steps": steps,
    }


def explain_node(graph: CodeGraph, query: str, *, limit: int = 30) -> dict[str, Any]:
    """Resolve a node and explain its strongest incoming and outgoing relationships."""
    node_id = resolve_node(graph, query)
    relationships: list[dict[str, Any]] = []
    for source, target, attributes in graph.in_edges(node_id, data=True):
        relationships.append(
            _relationship(graph, str(source), str(target), attributes, direction="incoming")
        )
    for source, target, attributes in graph.out_edges(node_id, data=True):
        relationships.append(
            _relationship(graph, str(source), str(target), attributes, direction="outgoing")
        )
    relationships.sort(
        key=lambda item: (-float(item["weight"]), str(item["relation"]), str(item["other"]))
    )
    return {
        "node": {"id": node_id, **dict(graph.nodes[node_id])},
        "degree": int(graph.degree(node_id)),
        "relationships": relationships[:limit],
    }


def resolve_node(graph: CodeGraph, query: str) -> str:
    """Resolve an exact or fuzzy node identifier, label, or qualified name."""
    normalized = query.strip().casefold()
    if not normalized:
        raise ValueError("Node query cannot be empty")
    exact = []
    choices: dict[str, str] = {}
    for node_id, attributes in graph.nodes(data=True):
        identifier = str(node_id)
        values = {
            identifier,
            str(attributes.get("label", "")),
            str(attributes.get("qualname", "")),
        }
        if normalized in {value.casefold() for value in values if value}:
            exact.append(identifier)
        choices[identifier] = " ".join(value for value in values if value)
    if exact:
        return sorted(exact)[0]
    match = process.extractOne(query, choices, scorer=fuzz.WRatio, score_cutoff=35)
    if match is None:
        raise ValueError(f"No graph node matches {query!r}")
    return str(match[2])


def _query_score(question: str, attributes: dict[str, Any]) -> float:
    document = " ".join(
        str(attributes.get(field, "")) for field in ("label", "qualname", "source_file", "kind")
    )
    return float(fuzz.WRatio(question, document))


def _relationship(
    graph: CodeGraph,
    source: str,
    target: str,
    attributes: dict[str, Any],
    *,
    direction: str,
) -> dict[str, Any]:
    other_id = source if direction == "incoming" else target
    return {
        "direction": direction,
        "other_id": other_id,
        "other": str(graph.nodes[other_id].get("label", other_id)),
        "relation": str(attributes.get("relation", "related")),
        "confidence": str(attributes.get("confidence", "INFERRED")),
        "source_location": str(attributes.get("source_location", "")),
        "weight": float(attributes.get("weight", 0.0)),
    }
