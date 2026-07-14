"""Ignore-aware, boundary-safe repository traversal."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pathspec import PathSpec

DEFAULT_EXCLUDES = (
    ".git/",
    ".contextforge/",
    ".venv/",
    "venv/",
    "node_modules/",
    "dist/",
    "build/",
    "__pycache__/",
    ".mypy_cache/",
    ".pytest_cache/",
    ".ruff_cache/",
)


@dataclass(frozen=True)
class TraversalConfig:
    """Controls safe repository source discovery."""

    extensions: frozenset[str] = frozenset({".py", ".pyi"})
    excludes: tuple[str, ...] = DEFAULT_EXCLUDES
    max_file_bytes: int = 2_000_000


def _ignore_spec(repository: Path, config: TraversalConfig) -> PathSpec:
    patterns = list(config.excludes)
    gitignore = repository / ".gitignore"
    if gitignore.is_file():
        patterns.extend(gitignore.read_text(encoding="utf-8", errors="replace").splitlines())
    contextignore = repository / ".contextforgeignore"
    if contextignore.is_file():
        patterns.extend(contextignore.read_text(encoding="utf-8", errors="replace").splitlines())
    return PathSpec.from_lines("gitwildmatch", patterns)


def discover_source_files(
    repository: Path, config: TraversalConfig | None = None
) -> tuple[Path, ...]:
    """Return deterministic source paths beneath *repository* that pass ignore rules."""
    config = config or TraversalConfig()
    root = repository.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(f"Repository path is not a directory: {root}")
    spec = _ignore_spec(root, config)
    discovered: list[Path] = []
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if spec.match_file(relative) or path.suffix.lower() not in config.extensions:
            continue
        try:
            if path.stat().st_size <= config.max_file_bytes:
                discovered.append(path)
        except OSError:
            continue
    return tuple(sorted(discovered, key=lambda candidate: candidate.relative_to(root).as_posix()))
