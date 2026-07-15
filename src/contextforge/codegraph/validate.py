"""Schema validation at the extraction/build boundary."""

from __future__ import annotations

from contextforge.codegraph.models import ConfidenceLabel, Extraction


def validate_extraction(extraction: Extraction) -> None:
    """Raise ``ValueError`` when an extractor emits an unsafe or invalid record."""
    if not extraction["path"] or not extraction["language"]:
        raise ValueError("Extraction path and language are required")
    node_ids: set[str] = set()
    for node in extraction["nodes"]:
        required = ("id", "label", "kind", "source_file", "source_location", "language")
        if any(not str(node.get(field, "")).strip() for field in required):
            raise ValueError(f"Invalid graph node in {extraction['path']}")
        if node["id"] in node_ids:
            raise ValueError(f"Duplicate graph node id: {node['id']}")
        node_ids.add(node["id"])
    for edge in extraction["edges"]:
        if not edge["source"] or not edge["relation"]:
            raise ValueError(f"Invalid graph edge in {extraction['path']}")
        if not edge["target"] and not edge.get("target_ref"):
            raise ValueError("Graph edge needs target or target_ref")
        try:
            ConfidenceLabel(edge["confidence"])
        except ValueError as error:
            raise ValueError(f"Invalid confidence label: {edge['confidence']}") from error
