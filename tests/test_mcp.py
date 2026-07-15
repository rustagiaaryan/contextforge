from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from contextforge.mcp.server import compile_task_context, get_symbol, index_repository, mcp

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    shutil.copytree(FIXTURE, repository, ignore=shutil.ignore_patterns(".contextforge"))
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


def test_mcp_stdio_transport_serves_every_tool(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    asyncio.run(_exercise_stdio_server(repository))


async def _exercise_stdio_server(repository: Path) -> None:
    expected_calls: list[tuple[str, dict[str, object]]] = [
        ("index_repository", {"repository": str(repository)}),
        ("get_index_status", {"repository": str(repository)}),
        (
            "search_symbols",
            {"repository": str(repository), "query": "Mount.resolve", "limit": 5},
        ),
        (
            "search_code",
            {"repository": str(repository), "query": "mounted route prefix", "limit": 5},
        ),
        (
            "get_symbol",
            {"repository": str(repository), "identifier": "app.routing.Mount.resolve"},
        ),
        (
            "get_callers",
            {"repository": str(repository), "identifier": "app.utils.join_path"},
        ),
        (
            "get_callees",
            {"repository": str(repository), "identifier": "app.routing.Mount.resolve"},
        ),
        (
            "find_related_tests",
            {
                "repository": str(repository),
                "identifier": "app.routing.Mount.resolve",
                "task": "mounted route prefix",
                "limit": 5,
            },
        ),
        (
            "search_git_history",
            {
                "repository": str(repository),
                "query": "mounted route prefix",
                "anchor_files": ["app/routing.py"],
                "limit": 5,
            },
        ),
        (
            "expand_graph_neighbors",
            {
                "repository": str(repository),
                "identifier": "app.routing.Mount.resolve",
                "max_depth": 2,
                "limit": 20,
            },
        ),
        (
            "compile_task_context",
            {
                "repository": str(repository),
                "task": "Mounted applications lose route prefixes.",
                "token_budget": 1_200,
                "output_format": "json",
            },
        ),
    ]
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "contextforge.cli", "mcp"],
        cwd=str(Path(__file__).parents[1]),
    )
    async with (
        stdio_client(server) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        initialized = await session.initialize()
        assert initialized.serverInfo.name == "ContextForge"
        listed = await session.list_tools()
        assert {tool.name for tool in listed.tools} == {name for name, _ in expected_calls}
        for name, arguments in expected_calls:
            result = await session.call_tool(name, arguments)
            assert not result.isError, f"{name}: {result.content}"
            if name == "compile_task_context":
                payload = json.loads(result.content[0].text)
                assert payload["estimated_tokens"] <= 1_200
                assert payload["items"]
