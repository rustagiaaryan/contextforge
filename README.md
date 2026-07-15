# ContextForge

[![CI](https://github.com/rustagiaaryan/contextforge/actions/workflows/ci.yml/badge.svg)](https://github.com/rustagiaaryan/contextforge/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg)](pyproject.toml)

ContextForge turns a code repository into an interactive knowledge graph and a compact evidence package for AI coding agents.

Instead of opening files one by one, an agent can search symbols, follow calls and imports, find related tests, inspect relevant Git history, and retrieve only the code needed for a task.

```text
repository
    ↓
Tree-sitter parsing
    ↓
classes · functions · imports · calls · inheritance
    ↓
NetworkX graph + architectural communities
    ↓
interactive HTML · JSON · Markdown · MCP tools
```

## What it does

- Builds a multi-language graph of files, classes, functions, methods, imports, calls, and inheritance
- Labels relationships as `EXTRACTED`, `INFERRED`, or `AMBIGUOUS`
- Groups strongly connected code into architectural communities
- Generates a standalone interactive graph with search, filters, node details, pan, and zoom
- Answers graph queries, explains components, and traces paths between symbols
- Compiles task-specific code, tests, and Git evidence under a requested token budget
- Exposes 11 typed tools through a local MCP server
- Runs locally without an API key, model download, vector database, or external graph service

## Quick start

ContextForge requires Python 3.11+ and [`uv`](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/rustagiaaryan/contextforge.git
cd contextforge
uv tool install .
```

Build a graph for any repository:

```bash
contextforge graph build ./repository
```

This creates:

```text
repository/contextforge-out/
├── graph.html       # interactive repository explorer
├── graph.json       # complete machine-readable graph
└── GRAPH_REPORT.md  # architecture summary
```

Open `graph.html` in a browser:

```bash
open repository/contextforge-out/graph.html       # macOS
xdg-open repository/contextforge-out/graph.html  # Linux
```

The custom SVG explorer uses a dark, community-colored layout. Search dims unrelated nodes, the community selector filters subsystems, and clicking a node shows its source location and incoming and outgoing relationships. The HTML is self-contained and works without a server.

## Explore the graph

```bash
# Return a focused subgraph for a question
contextforge graph query repository/contextforge-out/graph.json \
  --question "How does authentication reach the database?"

# Explain one component and its relationships
contextforge graph explain \
  repository/contextforge-out/graph.json UserService

# Find a static relationship path between two concepts
contextforge graph path \
  repository/contextforge-out/graph.json LoginRoute UserRepository
```

Graph queries use fuzzy symbol anchors followed by bounded structural expansion. They are deterministic and do not require an LLM.

## Compile context for an AI task

The graph explorer shows the whole architecture. For a specific bug or feature, ContextForge can instead create a small, explainable evidence package:

```bash
contextforge index ./repository

contextforge compile ./repository \
  --task "Mounted applications lose their route prefix" \
  --token-budget 8000 \
  --format markdown
```

The compiler combines BM25 search, fuzzy symbols, local vector retrieval, bounded graph expansion, related-test discovery, and confidence-gated Git history. An explainable reranker scores the results, then a diversity-aware optimizer selects source ranges while keeping the rendered estimate within the requested budget.

## MCP integration

Start the local stdio server:

```bash
contextforge mcp
```

Example client configuration:

```json
{
  "mcpServers": {
    "contextforge": {
      "command": "contextforge",
      "args": ["mcp"]
    }
  }
}
```

The server exposes:

```text
index_repository       get_index_status       search_symbols
search_code            get_symbol             get_callers
get_callees            find_related_tests     search_git_history
expand_graph_neighbors compile_task_context
```

Every tool accepts an explicit local repository path. The test suite launches the server as a subprocess, performs a real MCP handshake, discovers the schemas, and calls all 11 tools through stdio. See [docs/MCP.md](docs/MCP.md) for source-checkout configuration.

## How the graph is built

```text
detect → extract → build → resolve → cluster → analyze → export
```

1. Ignore-aware traversal finds supported files.
2. Tree-sitter extracts definitions and structural relationships without executing repository code.
3. NetworkX resolves local references into a directed multigraph.
4. Leiden clustering is used when installed; otherwise deterministic NetworkX modularity finds communities.
5. The exporter writes the complete JSON graph, a Markdown report, and the interactive HTML explorer.

The default installation supports 26 Tree-sitter grammar modes across 44 extensions, including Python, JavaScript, TypeScript, Go, Rust, Java, C/C++, C#, Kotlin, Ruby, PHP, Swift, Bash, and others. Python has the highest-fidelity task-retrieval index; multi-language graph extraction is best effort.

## Measured result

ContextForge was evaluated against 12 pinned historical fixes from Click, HTTPX, and Typer. At an 8,000-token budget, the full pipeline retrieved at least one file later changed by the developer in **11 of 12 tasks** and reduced the average estimated source context from **193,838 to 5,742 tokens (96.8%)**. All 12 packages stayed within budget.

This measures retrieval, not whether an AI generated a correct patch. The dataset is small and curated. Exact labels, definitions, ablations, and reproducible results are in [docs/EVALUATION.md](docs/EVALUATION.md).

## Development

```bash
uv sync --extra dev
uv run ruff format --check .
uv run ruff check .
uv run mypy src/contextforge
uv run pytest -q
```

Useful details:

- [Architecture](docs/ARCHITECTURE.md)
- [Graph workflow](docs/GRAPH.md)
- [MCP tools](docs/MCP.md)
- [Reproducible demo](docs/DEMO.md)
- [Evaluation](docs/EVALUATION.md)

## Current limitations

- Dynamic dispatch and runtime imports cannot always be resolved statically.
- The portable graph is rebuilt rather than incrementally patched.
- Graph queries return structured evidence, not generated prose answers.
- The default local vector provider uses feature hashing rather than a trained embedding model.
- The benchmark measures retrieval quality, not downstream patch success.
