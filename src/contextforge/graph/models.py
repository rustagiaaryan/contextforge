"""Typed knowledge-graph records."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from contextforge.models import EdgeType, NodeType


class GraphNode(BaseModel):
    """A stored graph node, optionally backed by a source unit."""

    model_config = ConfigDict(frozen=True)

    node_id: str
    node_type: NodeType
    path: str | None = None
    label: str
    unit_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    """A directed, confidence-weighted graph relationship."""

    model_config = ConfigDict(frozen=True)

    source_id: str
    target_id: str
    edge_type: EdgeType
    confidence: float = Field(ge=0.0, le=1.0)
    metadata: dict[str, object] = Field(default_factory=dict)


class GraphNeighbor(BaseModel):
    """A graph node reached during bounded expansion."""

    model_config = ConfigDict(frozen=True)

    node: GraphNode
    distance: int = Field(ge=1)
    via_edge: EdgeType
    direction: str
    confidence: float = Field(ge=0.0, le=1.0)
