"""Markdown rendering for graph-first repository analysis."""

from __future__ import annotations

from contextforge.codegraph.models import GraphSummary


def render_report(repository_name: str, summary: GraphSummary, *, timings: dict[str, float]) -> str:
    """Render a compact, deterministic architecture report."""
    lines = [
        f"# {repository_name} knowledge graph",
        "",
        "> Generated locally by ContextForge from deterministic Tree-sitter extraction.",
        "",
        "## Overview",
        "",
        f"- Nodes: **{summary['node_count']:,}**",
        f"- Relationships: **{summary['edge_count']:,}**",
        f"- Communities: **{summary['community_count']:,}**",
        "- Confidence: "
        + ", ".join(f"{label} {count:,}" for label, count in summary["confidence_counts"].items()),
        "- Pipeline: "
        + ", ".join(f"{stage} {latency:.1f} ms" for stage, latency in timings.items()),
        "",
        "## Central concepts",
        "",
        "| Concept | Kind | Degree | Source |",
        "| --- | --- | ---: | --- |",
    ]
    for node in summary["god_nodes"]:
        lines.append(
            f"| `{node['label']}` | {node['kind']} | {node['degree']} | "
            f"`{node['source_file'] or 'external'}` |"
        )
    lines.extend(["", "## Communities", ""])
    for community in summary["communities"]:
        top_nodes = ", ".join(f"`{name}`" for name in community["top_nodes"])
        lines.append(
            f"- **Community {community['id']} — {community['label']}** "
            f"({community['size']} nodes): {top_nodes}"
        )
    lines.extend(
        [
            "",
            "## Cross-community connections",
            "",
            "| Source | Relationship | Target | Confidence |",
            "| --- | --- | --- | --- |",
        ]
    )
    for edge in summary["cross_community_edges"]:
        lines.append(
            f"| `{edge['source']}` | {edge['relation']} | `{edge['target']}` | "
            f"{edge['confidence']} |"
        )
    lines.extend(["", "## Suggested graph questions", ""])
    lines.extend(f"- {question}" for question in summary["suggested_questions"])
    lines.extend(
        [
            "",
            "## Confidence model",
            "",
            "- `EXTRACTED`: explicitly present in source text.",
            "- `INFERRED`: resolved by a deterministic second pass.",
            "- `AMBIGUOUS`: multiple targets remain plausible and require review.",
            "",
        ]
    )
    return "\n".join(lines)
