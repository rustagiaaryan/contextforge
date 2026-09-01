"""Deterministic graph-centrality utilities without optional numeric dependencies."""

from __future__ import annotations

import networkx as nx


def normalized_weighted_pagerank(
    graph: nx.DiGraph,
    *,
    damping: float = 0.85,
    tolerance: float = 1e-10,
    max_iterations: int = 100,
) -> dict[str, float]:
    """Return weighted PageRank normalized so the strongest node scores ``1.0``."""
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
    maximum = max(ranks.values(), default=1.0)
    return {
        node_id: round(score / maximum, 12) if maximum else 0.0 for node_id, score in ranks.items()
    }
