"""ContextForge configuration."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class ContextForgeConfig(BaseModel):
    """Runtime configuration with safe repository-local defaults."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    database_dir: str = ".contextforge"
    max_file_bytes: int = Field(default=2_000_000, ge=1)
    graph_max_depth: int = Field(default=2, ge=0, le=5)
    graph_max_nodes: int = Field(default=40, ge=1, le=500)
    semantic_dimensions: int = Field(default=384, ge=32, le=4096)
    embedding_provider: str = "local"

    @classmethod
    def from_environment(cls, base: ContextForgeConfig | None = None) -> ContextForgeConfig:
        """Apply documented `CONTEXTFORGE_*` overrides to optional base values."""
        values: dict[str, object] = base.model_dump() if base else {}
        if value := os.getenv("CONTEXTFORGE_DB_DIR"):
            values["database_dir"] = value
        if value := os.getenv("CONTEXTFORGE_EMBEDDING_PROVIDER"):
            values["embedding_provider"] = value
        integer_variables = {
            "CONTEXTFORGE_MAX_FILE_BYTES": "max_file_bytes",
            "CONTEXTFORGE_GRAPH_MAX_DEPTH": "graph_max_depth",
            "CONTEXTFORGE_GRAPH_MAX_NODES": "graph_max_nodes",
            "CONTEXTFORGE_SEMANTIC_DIMENSIONS": "semantic_dimensions",
        }
        for environment_name, field_name in integer_variables.items():
            if value := os.getenv(environment_name):
                try:
                    values[field_name] = int(value)
                except ValueError as error:
                    raise ValueError(f"{environment_name} must be an integer") from error
        return cls.model_validate(values)

    @classmethod
    def from_repository(cls, repository: Path) -> ContextForgeConfig:
        """Load `.contextforge.toml`, then apply environment overrides."""
        path = repository / ".contextforge.toml"
        if not path.is_file():
            return cls.from_environment()
        try:
            document = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as error:
            raise ValueError(f"Cannot load {path.name}: {error}") from error
        section = document.get("contextforge", document)
        if not isinstance(section, dict):
            raise ValueError(".contextforge.toml [contextforge] must be a table")
        base = cls.model_validate(section)
        return cls.from_environment(base)

    def database_path(self, repository: Path) -> Path:
        """Return the index database path for a repository."""
        return repository / self.database_dir / "index.sqlite3"
