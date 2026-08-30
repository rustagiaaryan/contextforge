"""Stable models shared by impact APIs, CLI output, and MCP tools."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from contextforge.models import EdgeType


class RiskLevel(StrEnum):
    """Explainable blast-radius classification."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ImpactStep(BaseModel):
    """One dependency edge in an impact explanation path."""

    model_config = ConfigDict(frozen=True)

    source_id: str
    target_id: str
    edge_type: EdgeType
    confidence: float = Field(ge=0.0, le=1.0)


class ImpactSeed(BaseModel):
    """An indexed source unit where impact traversal begins."""

    model_config = ConfigDict(frozen=True)

    unit_id: str
    qualname: str
    path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)


class ImpactedSymbol(ImpactSeed):
    """A symbol reached from an impact seed with full provenance."""

    distance: int = Field(ge=1, le=3)
    path_confidence: float = Field(ge=0.0, le=1.0)
    relationship_path: tuple[ImpactStep, ...]
    is_test: bool = False
    community: int | None = None


class ImpactReport(BaseModel):
    """Complete bounded impact report returned by every public interface."""

    model_config = ConfigDict(frozen=True)

    repository: str
    mode: Literal["symbol", "changes"]
    target: str
    max_depth: int = Field(ge=1, le=3)
    limit: int = Field(ge=1, le=200)
    seeds: tuple[ImpactSeed, ...]
    impacted: tuple[ImpactedSymbol, ...]
    related_tests: tuple[ImpactedSymbol, ...]
    impacted_files: tuple[str, ...]
    changed_files: tuple[str, ...]
    communities: tuple[int, ...]
    unresolved: tuple[str, ...]
    risk_level: RiskLevel
    risk_reasons: tuple[str, ...]
    truncated: bool
