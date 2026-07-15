"""Deterministic graph community detection with an optional Leiden backend."""

from __future__ import annotations

from collections.abc import Iterable

import networkx as nx

from contextforge.codegraph.models import CodeGraph, SimpleGraph


def cluster_graph(graph: CodeGraph, *, backend: str = "auto") -> CodeGraph:
    """Assign a stable integer ``community`` attribute to every node."""
    if backend not in {"auto", "leiden", "networkx"}:
        raise ValueError("Cluster backend must be auto, leiden, or networkx")
    simple = _undirected(graph)
    communities: list[set[str]]
    used_backend = "networkx"
    if backend in {"auto", "leiden"}:
        try:
            communities = _leiden(simple)
            used_backend = "leiden"
        except (ImportError, RuntimeError):
            if backend == "leiden":
                raise
            communities = _networkx_communities(simple)
    else:
        communities = _networkx_communities(simple)
    communities.sort(key=lambda group: (-len(group), min(group, default="")))
    for community_id, members in enumerate(communities):
        for node_id in sorted(members):
            graph.nodes[node_id]["community"] = community_id
    graph.graph["cluster_backend"] = used_backend
    graph.graph["community_count"] = len(communities)
    return graph


def _undirected(graph: CodeGraph) -> SimpleGraph:
    simple: SimpleGraph = nx.Graph()
    simple.add_nodes_from(str(node) for node in graph.nodes)
    for source, target, attributes in graph.edges(data=True):
        if source == target:
            continue
        weight = float(attributes.get("weight", 1.0))
        previous = float(simple.get_edge_data(source, target, {}).get("weight", 0.0))
        simple.add_edge(str(source), str(target), weight=previous + weight)
    return simple


def _networkx_communities(graph: SimpleGraph) -> list[set[str]]:
    if not graph.nodes:
        return []
    if not graph.edges:
        return [{str(node)} for node in sorted(graph.nodes)]
    groups: Iterable[set[str] | frozenset[str]] = nx.community.greedy_modularity_communities(
        graph,
        weight="weight",
        resolution=1.0,
    )
    return [{str(node) for node in group} for group in groups]


def _leiden(graph: SimpleGraph) -> list[set[str]]:
    try:
        from graspologic.partition import hierarchical_leiden  # type: ignore[import-not-found]
    except ImportError as error:
        raise ImportError("Install ContextForge with the 'leiden' extra") from error
    try:
        records = hierarchical_leiden(graph, random_seed=0)
        assignments = {
            str(record.node): int(record.cluster)
            for record in records
            if bool(record.is_final_cluster)
        }
    except Exception as error:
        raise RuntimeError(f"Leiden clustering failed: {error}") from error
    if len(assignments) != graph.number_of_nodes():
        raise RuntimeError("Leiden did not assign every graph node")
    grouped: dict[int, set[str]] = {}
    for node_id, community in assignments.items():
        grouped.setdefault(community, set()).add(node_id)
    return list(grouped.values())
