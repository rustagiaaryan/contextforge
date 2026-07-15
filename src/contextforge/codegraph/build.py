"""Resolve extraction dictionaries into a queryable NetworkX graph."""

from __future__ import annotations

from collections import defaultdict
from pathlib import PurePosixPath

from contextforge.codegraph.models import (
    CONFIDENCE_WEIGHTS,
    ArtifactEdge,
    CodeGraph,
    ConfidenceLabel,
    Extraction,
)
from contextforge.codegraph.validate import validate_extraction


def build_graph(extractions: list[Extraction]) -> CodeGraph:
    """Build a directed graph and resolve cross-file references in a bounded second pass."""
    graph = CodeGraph()
    for extraction in extractions:
        validate_extraction(extraction)
        for node in extraction["nodes"]:
            graph.add_node(node["id"], **dict(node))

    by_label: dict[str, list[str]] = defaultdict(list)
    by_qualname: dict[str, list[str]] = defaultdict(list)
    by_module: dict[str, list[str]] = defaultdict(list)
    for node_id, attributes in graph.nodes(data=True):
        label = str(attributes.get("label", ""))
        qualname = str(attributes.get("qualname", ""))
        if label:
            by_label[_normalize(label)].append(str(node_id))
        if qualname:
            by_qualname[_normalize(qualname)].append(str(node_id))
        if attributes.get("kind") == "file":
            path = PurePosixPath(str(attributes.get("source_file", "")))
            module = path.with_suffix("").as_posix().replace("/", ".")
            by_module[_normalize(module)].append(str(node_id))
            by_module[_normalize(path.stem)].append(str(node_id))

    for extraction in extractions:
        for edge in extraction["edges"]:
            if edge["target"] and edge["target"] in graph:
                _add_edge(graph, edge, edge["target"], ConfidenceLabel(edge["confidence"]))
                continue
            target_ref = edge.get("target_ref", "")
            candidates = _resolve_candidates(
                graph,
                edge,
                target_ref,
                by_label=by_label,
                by_qualname=by_qualname,
                by_module=by_module,
            )
            if len(candidates) == 1:
                label = ConfidenceLabel(edge["confidence"])
                if edge["relation"] in {"calls", "inherits"}:
                    label = ConfidenceLabel.INFERRED
                _add_edge(graph, edge, candidates[0], label)
            elif candidates:
                for candidate in candidates[:5]:
                    _add_edge(graph, edge, candidate, ConfidenceLabel.AMBIGUOUS)
            elif target_ref:
                target_id = _external_node_id(edge["relation"], target_ref)
                if target_id not in graph:
                    graph.add_node(
                        target_id,
                        id=target_id,
                        label=target_ref,
                        kind="external",
                        source_file="",
                        source_location="",
                        language="external",
                        qualname=target_ref,
                        external=True,
                    )
                _add_edge(
                    graph,
                    edge,
                    target_id,
                    ConfidenceLabel(edge["confidence"]),
                )
    graph.graph.update(
        schema_version=1,
        extraction_count=len(extractions),
        languages=sorted({extraction["language"] for extraction in extractions}),
    )
    return graph


def _resolve_candidates(
    graph: CodeGraph,
    edge: ArtifactEdge,
    target_ref: str,
    *,
    by_label: dict[str, list[str]],
    by_qualname: dict[str, list[str]],
    by_module: dict[str, list[str]],
) -> list[str]:
    normalized = _normalize(target_ref)
    final_name = _normalize(target_ref.rsplit(".", 1)[-1].rsplit("::", 1)[-1])
    candidates = list(dict.fromkeys(by_qualname.get(normalized, [])))
    if edge["relation"] == "imports":
        candidates.extend(
            candidate for candidate in by_module.get(normalized, []) if candidate not in candidates
        )
    candidates.extend(
        candidate for candidate in by_label.get(final_name, []) if candidate not in candidates
    )
    if len(candidates) <= 1:
        return candidates
    source_path = str(graph.nodes[edge["source"]].get("source_file", ""))
    same_file = [
        candidate
        for candidate in candidates
        if str(graph.nodes[candidate].get("source_file", "")) == source_path
    ]
    return same_file if len(same_file) == 1 else sorted(candidates)


def _add_edge(
    graph: CodeGraph,
    edge: ArtifactEdge,
    target: str,
    confidence: ConfidenceLabel,
) -> None:
    key = f"{edge['relation']}:{edge['source_location']}:{target}"
    graph.add_edge(
        edge["source"],
        target,
        key=key,
        relation=edge["relation"],
        confidence=confidence.value,
        source_location=edge["source_location"],
        target_ref=edge.get("target_ref", ""),
        weight=CONFIDENCE_WEIGHTS[confidence],
    )


def _normalize(value: str) -> str:
    return value.strip().strip("'\"`./").replace("/", ".").casefold()


def _external_node_id(relation: str, target_ref: str) -> str:
    normalized = _normalize(target_ref).replace(" ", "-")
    return f"external:{relation}:{normalized}"
