"""Shared typed models used across the ContextForge pipeline."""

from __future__ import annotations

from enum import StrEnum
from hashlib import sha256

from pydantic import BaseModel, ConfigDict, Field, computed_field


class NodeType(StrEnum):
    """Knowledge-graph node types."""

    REPOSITORY = "repository"
    DIRECTORY = "directory"
    FILE = "file"
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    TEST = "test"
    COMMIT = "commit"


class EdgeType(StrEnum):
    """Knowledge-graph relationship types."""

    CONTAINS = "CONTAINS"
    IMPORTS = "IMPORTS"
    CALLS = "CALLS"
    INHERITS = "INHERITS"
    DEFINES = "DEFINES"
    REFERENCES = "REFERENCES"
    TESTS = "TESTS"
    CHANGED_IN = "CHANGED_IN"
    CO_CHANGED_WITH = "CO_CHANGED_WITH"


class SourceUnit(BaseModel):
    """A persistable source or graph unit with a stable logical identifier."""

    model_config = ConfigDict(frozen=True)

    unit_id: str
    node_type: NodeType
    path: str
    name: str
    qualname: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    signature: str = ""
    docstring: str = ""
    language: str = "python"
    content: str = ""
    content_hash: str
    parent_id: str | None = None
    is_test: bool = False

    @computed_field  # type: ignore[prop-decorator]
    @property
    def estimated_tokens(self) -> int:
        """Return a conservative, deterministic source token estimate."""
        return max(1, (len(self.content) + 3) // 4)

    @classmethod
    def make_id(cls, node_type: NodeType, path: str, qualname: str) -> str:
        """Build a stable identifier independent of source line movement."""
        return f"{node_type.value}:{path}:{qualname}"

    @classmethod
    def hash_content(cls, content: str) -> str:
        """Hash text using the cache and invalidation digest."""
        return sha256(content.encode("utf-8", errors="replace")).hexdigest()


class RelationHint(BaseModel):
    """An unresolved parser relationship resolved during graph indexing."""

    model_config = ConfigDict(frozen=True)

    source_id: str
    edge_type: EdgeType
    target: str
    line: int | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class ParsedFile(BaseModel):
    """Complete parser result for one repository file."""

    model_config = ConfigDict(frozen=True)

    path: str
    content_hash: str
    units: tuple[SourceUnit, ...]
    relations: tuple[RelationHint, ...]


class IndexStats(BaseModel):
    """Summary of an indexing run."""

    discovered_files: int = 0
    parsed_files: int = 0
    unchanged_files: int = 0
    deleted_files: int = 0
    units_indexed: int = 0
    parse_errors: tuple[str, ...] = ()
    elapsed_ms: float = 0.0
