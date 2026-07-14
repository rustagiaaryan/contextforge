from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

from contextforge.mcp.server import compile_task_context, get_symbol, index_repository, mcp

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    shutil.copytree(FIXTURE, repository)
    return repository


def test_mcp_registers_the_documented_tool_surface() -> None:
    tools = asyncio.run(mcp.list_tools())
    names = {tool.name for tool in tools}
    assert names == {
        "compile_task_context",
        "expand_graph_neighbors",
        "find_related_tests",
        "get_callees",
        "get_callers",
        "get_index_status",
        "get_symbol",
        "index_repository",
        "search_code",
        "search_git_history",
        "search_symbols",
    }


def test_mcp_tools_index_fetch_symbols_and_compile(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    report = index_repository(str(repository))
    symbol = get_symbol(str(repository), "app.routing.Mount.resolve")
    package = json.loads(
        compile_task_context(
            str(repository),
            "Mounted applications lose route prefixes.",
            token_budget=1_200,
        )
    )

    assert report["source"]["parsed_files"] == 4
    assert symbol["found"] is True
    assert symbol["unit"]["signature"] == "def resolve(self, path: str)"
    assert package["estimated_tokens"] <= 1_200
    assert package["items"]
