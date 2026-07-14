"""Typed Model Context Protocol tools backed by the ContextForge engine."""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from contextforge import ContextForge
from contextforge.graph import GraphQuery
from contextforge.models import EdgeType, SourceUnit
from contextforge.retrieval import GitHistoryRetriever, RelatedTestRetriever

mcp = FastMCP(
    "ContextForge",
    instructions=(
        "Index local source repositories and retrieve compact, task-specific evidence. "
        "Repository contents are parsed as untrusted data and are never executed."
    ),
)


def _engine(repository: str, *, require_index: bool = True) -> ContextForge:
    engine = ContextForge.open(repository)
    if require_index and not engine.get_index_status().indexed:
        engine.index()
    return engine


def _find_unit(engine: ContextForge, identifier: str) -> SourceUnit | None:
    direct = engine.database.get_unit(identifier)
    if direct:
        return direct
    units = engine.database.list_units()
    exact = [unit for unit in units if unit.qualname == identifier]
    if exact:
        return exact[0]
    named = [unit for unit in units if unit.name == identifier]
    return named[0] if len(named) == 1 else None


@mcp.tool()
def index_repository(repository: str) -> dict[str, Any]:
    """Incrementally index one local repository path; never imports or executes its code."""
    return _engine(repository, require_index=False).index().model_dump(mode="json")


@mcp.tool()
def get_index_status(repository: str) -> dict[str, Any]:
    """Return persistent file, symbol, graph, embedding, commit, and parse-error counts."""
    return _engine(repository, require_index=False).get_index_status().model_dump(mode="json")


@mcp.tool()
def search_symbols(repository: str, query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Find exact or fuzzy classes, functions, methods, and tests with ranked provenance."""
    results = _engine(repository).search_symbols(query, limit=min(100, max(1, limit)))
    return [candidate.model_dump(mode="json") for candidate in results]


@mcp.tool()
def search_code(repository: str, query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Run hybrid BM25 and local-embedding search over paths, docs, symbols, and source."""
    results = _engine(repository).search_code(query, limit=min(100, max(1, limit)))
    return [candidate.model_dump(mode="json") for candidate in results]


@mcp.tool()
def get_symbol(repository: str, identifier: str) -> dict[str, Any]:
    """Get a symbol by stable ID or fully qualified name, including incoming/outgoing edges."""
    engine = _engine(repository)
    unit = _find_unit(engine, identifier)
    if unit is None:
        return {"found": False, "identifier": identifier}
    incoming, outgoing = GraphQuery(engine.database).edges(unit.unit_id)
    return {
        "found": True,
        "unit": unit.model_dump(mode="json"),
        "incoming": [edge.model_dump(mode="json") for edge in incoming],
        "outgoing": [edge.model_dump(mode="json") for edge in outgoing],
    }


@mcp.tool()
def get_callers(repository: str, identifier: str) -> list[dict[str, Any]]:
    """Return locally resolved callers of a stable symbol ID or fully qualified name."""
    engine = _engine(repository)
    unit = _find_unit(engine, identifier)
    if unit is None:
        return []
    return [
        node.model_dump(mode="json") for node in GraphQuery(engine.database).callers(unit.unit_id)
    ]


@mcp.tool()
def get_callees(repository: str, identifier: str) -> list[dict[str, Any]]:
    """Return locally resolved callees of a stable symbol ID or fully qualified name."""
    engine = _engine(repository)
    unit = _find_unit(engine, identifier)
    if unit is None:
        return []
    return [
        node.model_dump(mode="json") for node in GraphQuery(engine.database).callees(unit.unit_id)
    ]


@mcp.tool()
def find_related_tests(
    repository: str, identifier: str, task: str = "", limit: int = 12
) -> list[dict[str, Any]]:
    """Find tests related to one implementation symbol using graph, names, paths, and task text."""
    engine = _engine(repository)
    unit = _find_unit(engine, identifier)
    if unit is None:
        return []
    results = RelatedTestRetriever(engine.database).find(
        [unit], task=task, limit=min(50, max(1, limit))
    )
    return [candidate.model_dump(mode="json") for candidate in results]


@mcp.tool()
def search_git_history(
    repository: str,
    query: str,
    anchor_files: list[str] | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Return confidence-gated historical changes related to a task and current anchor files."""
    engine = _engine(repository)
    results = GitHistoryRetriever(engine.database, provider=engine.embedding_provider).search(
        query,
        anchor_paths=set(anchor_files or []),
        limit=min(30, max(1, limit)),
    )
    return [commit.model_dump(mode="json") for commit in results]


@mcp.tool()
def expand_graph_neighbors(
    repository: str,
    identifier: str,
    edge_types: list[str] | None = None,
    max_depth: int = 1,
    limit: int = 40,
) -> list[dict[str, Any]]:
    """Expand a bounded local graph neighborhood; depth is capped at 3 and nodes at 200."""
    engine = _engine(repository)
    unit = _find_unit(engine, identifier)
    if unit is None:
        return []
    try:
        selected_edges = {EdgeType(value.upper()) for value in edge_types} if edge_types else None
    except ValueError as error:
        valid = ", ".join(edge.value for edge in EdgeType)
        raise ValueError(f"Unknown edge type. Valid values: {valid}") from error
    neighbors = GraphQuery(engine.database).neighbors(
        unit.unit_id,
        edge_types=selected_edges,
        max_depth=min(3, max(1, max_depth)),
        limit=min(200, max(1, limit)),
    )
    return [neighbor.model_dump(mode="json") for neighbor in neighbors]


@mcp.tool()
def compile_task_context(
    repository: str,
    task: str,
    token_budget: int = 8_000,
    output_format: Literal["json", "markdown"] = "json",
) -> str:
    """Compile a complete explainable package under a strict 512-200000 token budget."""
    bounded_budget = min(200_000, max(512, token_budget))
    package = _engine(repository).compile_context(task=task, token_budget=bounded_budget)
    return package.to_markdown() if output_format == "markdown" else package.to_json()
