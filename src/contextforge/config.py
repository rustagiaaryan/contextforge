"""ContextForge configuration."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class ContextForgeConfig(BaseModel):
    """Runtime configuration with safe repository-local defaults."""

    model_config = ConfigDict(frozen=True)

    database_dir: str = ".contextforge"
    max_file_bytes: int = Field(default=2_000_000, ge=1)
    graph_max_depth: int = Field(default=2, ge=0, le=5)
    graph_max_nodes: int = Field(default=40, ge=1, le=500)
    semantic_dimensions: int = Field(default=384, ge=32, le=4096)
    embedding_provider: str = "local"

    @classmethod
    def from_environment(cls) -> ContextForgeConfig:
        """Load documented `CONTEXTFORGE_*` environment overrides."""
        values: dict[str, object] = {}
        if value := os.getenv("CONTEXTFORGE_DB_DIR"):
            values["database_dir"] = value
        if value := os.getenv("CONTEXTFORGE_EMBEDDING_PROVIDER"):
            values["embedding_provider"] = value
        return cls.model_validate(values)

    def database_path(self, repository: Path) -> Path:
        """Return the index database path for a repository."""
        return repository / self.database_dir / "index.sqlite3"
