"""Plain, validated records shared by graph-artifact pipeline stages."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any, NotRequired, TypeAlias, TypedDict

import networkx as nx

GraphAttributes: TypeAlias = dict[str, Any]
if TYPE_CHECKING:
    CodeGraph: TypeAlias = nx.MultiDiGraph[str, GraphAttributes, GraphAttributes]
    SimpleGraph: TypeAlias = nx.Graph[str, GraphAttributes, GraphAttributes]
else:
    CodeGraph: TypeAlias = nx.MultiDiGraph
    SimpleGraph: TypeAlias = nx.Graph


class ConfidenceLabel(StrEnum):
    """Describe whether a graph relationship was read or resolved."""

    EXTRACTED = "EXTRACTED"
    INFERRED = "INFERRED"
    AMBIGUOUS = "AMBIGUOUS"


class ArtifactNode(TypedDict):
    """Serializable graph node emitted by language extractors."""

    id: str
    label: str
    kind: str
    source_file: str
    source_location: str
    language: str
    qualname: NotRequired[str]
    signature: NotRequired[str]
    start_line: NotRequired[int]
    end_line: NotRequired[int]
    external: NotRequired[bool]


class ArtifactEdge(TypedDict):
    """Serializable relationship, potentially awaiting symbol resolution."""

    source: str
    target: str
    relation: str
    confidence: str
    source_location: str
    target_ref: NotRequired[str]
    weight: NotRequired[float]


class Extraction(TypedDict):
    """Complete extraction result for one source file."""

    path: str
    language: str
    nodes: list[ArtifactNode]
    edges: list[ArtifactEdge]
    parse_errors: list[str]


class GodNodeSummary(TypedDict):
    """One high-degree concept in the generated graph."""

    id: str
    label: str
    kind: str
    degree: int
    source_file: str


class CommunitySummary(TypedDict):
    """One detected repository subsystem."""

    id: int
    size: int
    label: str
    top_nodes: list[str]


class CrossCommunitySummary(TypedDict):
    """One relationship crossing detected subsystem boundaries."""

    source: str
    target: str
    relation: str
    confidence: str
    score: int


class GraphSummary(TypedDict):
    """Compact analysis data rendered into reports and JSON metadata."""

    node_count: int
    edge_count: int
    community_count: int
    relation_counts: dict[str, int]
    confidence_counts: dict[str, int]
    god_nodes: list[GodNodeSummary]
    communities: list[CommunitySummary]
    cross_community_edges: list[CrossCommunitySummary]
    suggested_questions: list[str]


CONFIDENCE_WEIGHTS: dict[ConfidenceLabel, float] = {
    ConfidenceLabel.EXTRACTED: 1.0,
    ConfidenceLabel.INFERRED: 0.72,
    ConfidenceLabel.AMBIGUOUS: 0.4,
}
