"""Local, deterministic graph analysis for reports and agent queries."""

from __future__ import annotations

from collections import Counter, defaultdict

from contextforge.codegraph.models import (
    CodeGraph,
    CommunitySummary,
    CrossCommunitySummary,
    GodNodeSummary,
    GraphSummary,
)


def analyze_graph(graph: CodeGraph, *, limit: int = 12) -> GraphSummary:
    """Identify central nodes, communities, and cross-subsystem connections."""
    degrees = sorted(
        ((str(node), int(degree)) for node, degree in graph.degree()),
        key=lambda item: (-item[1], item[0]),
    )
    god_nodes: list[GodNodeSummary] = [
        {
            "id": node_id,
            "label": str(graph.nodes[node_id].get("label", node_id)),
            "kind": str(graph.nodes[node_id].get("kind", "unknown")),
            "degree": degree,
            "source_file": str(graph.nodes[node_id].get("source_file", "")),
        }
        for node_id, degree in degrees[:limit]
    ]
    grouped: dict[int, list[str]] = defaultdict(list)
    for node_id, attributes in graph.nodes(data=True):
        grouped[int(attributes.get("community", -1))].append(str(node_id))
    communities: list[CommunitySummary] = []
    for community_id, members in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        ranked = sorted(members, key=lambda node_id: (-int(graph.degree(node_id)), node_id))
        communities.append(
            {
                "id": community_id,
                "size": len(members),
                "label": _community_label(graph, ranked),
                "top_nodes": [str(graph.nodes[node].get("label", node)) for node in ranked[:5]],
            }
        )
    relation_counts: Counter[str] = Counter()
    confidence_counts: Counter[str] = Counter()
    cross_edges: list[CrossCommunitySummary] = []
    for source, target, attributes in graph.edges(data=True):
        relation = str(attributes.get("relation", "related"))
        confidence = str(attributes.get("confidence", "INFERRED"))
        relation_counts[relation] += 1
        confidence_counts[confidence] += 1
        source_community = graph.nodes[source].get("community")
        target_community = graph.nodes[target].get("community")
        if source_community == target_community:
            continue
        cross_edges.append(
            {
                "source": str(graph.nodes[source].get("label", source)),
                "target": str(graph.nodes[target].get("label", target)),
                "relation": relation,
                "confidence": confidence,
                "score": int(graph.degree(source)) + int(graph.degree(target)),
            }
        )
    cross_edges.sort(key=lambda item: (-item["score"], item["source"], item["target"]))
    questions = _suggest_questions(god_nodes, communities, cross_edges)
    return GraphSummary(
        node_count=graph.number_of_nodes(),
        edge_count=graph.number_of_edges(),
        community_count=len(grouped),
        relation_counts=dict(sorted(relation_counts.items())),
        confidence_counts=dict(sorted(confidence_counts.items())),
        god_nodes=god_nodes,
        communities=communities,
        cross_community_edges=cross_edges[:limit],
        suggested_questions=questions,
    )


def _community_label(graph: CodeGraph, ranked: list[str]) -> str:
    labels = [
        str(graph.nodes[node].get("label", ""))
        for node in ranked
        if not bool(graph.nodes[node].get("external", False))
    ]
    return " / ".join(label for label in labels[:3] if label) or "External dependencies"


def _suggest_questions(
    god_nodes: list[GodNodeSummary],
    communities: list[CommunitySummary],
    cross_edges: list[CrossCommunitySummary],
) -> list[str]:
    questions: list[str] = []
    if god_nodes:
        questions.append(f"Why is {god_nodes[0]['label']} central to this repository?")
    if len(communities) > 1:
        first_label = communities[0]["label"]
        second_label = communities[1]["label"]
        questions.append(f"How do the {first_label} and {second_label} subsystems interact?")
    if cross_edges:
        edge = cross_edges[0]
        relation = edge["relation"]
        source = edge["source"]
        target = edge["target"]
        questions.append(f"Trace the {relation} relationship between {source} and {target}.")
    questions.append("Which extracted relationships are ambiguous and need human review?")
    return questions[:5]
