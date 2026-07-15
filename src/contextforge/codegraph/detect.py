"""Ignore-aware file discovery for the multi-language graph pipeline."""

from __future__ import annotations

from pathlib import Path

from contextforge.indexing.traversal import TraversalConfig, discover_source_files

CODE_EXTENSIONS = frozenset(
    {
        ".bash",
        ".c",
        ".cc",
        ".cjs",
        ".cpp",
        ".cs",
        ".cxx",
        ".ex",
        ".exs",
        ".f",
        ".f03",
        ".f08",
        ".f90",
        ".f95",
        ".go",
        ".groovy",
        ".h",
        ".hpp",
        ".java",
        ".jl",
        ".js",
        ".json",
        ".jsx",
        ".kt",
        ".kts",
        ".lua",
        ".m",
        ".mjs",
        ".mm",
        ".php",
        ".ps1",
        ".psm1",
        ".py",
        ".pyi",
        ".rb",
        ".rs",
        ".scala",
        ".sh",
        ".swift",
        ".ts",
        ".tsx",
        ".v",
        ".verilog",
        ".zig",
    }
)


def collect_files(root: Path, *, max_file_bytes: int = 2_000_000) -> tuple[Path, ...]:
    """Collect deterministic, ignored-filtered source paths beneath *root*."""
    return discover_source_files(
        root,
        TraversalConfig(extensions=CODE_EXTENSIONS, max_file_bytes=max_file_bytes),
    )
