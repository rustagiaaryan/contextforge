# ContextForge

[![CI](https://github.com/rustagiaaryan/contextforge/actions/workflows/ci.yml/badge.svg)](https://github.com/rustagiaaryan/contextforge/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

ContextForge turns a software repository into an interactive, queryable knowledge graph that AI coding agents can use to understand the project.

Instead of repeatedly searching through files, an agent can use ContextForge to:

- Find important classes, functions, modules, and services
- Understand how components depend on one another
- Trace static call and import paths across files
- Identify architectural subsystems
- Retrieve only the part of a codebase relevant to a question
- Explore code structure through an interactive graph and machine-readable interface

ContextForge can be used directly from the command line or exposed as an MCP server for tools such as Claude Code, Codex, Cursor, and other MCP-compatible coding agents.

---

## Why ContextForge?

AI coding agents are good at analyzing individual files, but understanding an entire repository is more difficult.

A single feature may involve:

- An API route in one file
- Business logic in another module
- A model elsewhere
- Configuration and infrastructure code
- Tests that describe the expected behavior

ContextForge connects these pieces into a structured graph.

For example:

```text
LoginRoute
    └── calls ──> authenticate_user()
                       ├── calls ──> load_user()
                       ├── calls ──> verify_password()
                       └── calls ──> create_access_token()
```

Each node represents something meaningful in the project, while each edge describes a relationship between two nodes.

This allows developers and coding agents to navigate the repository by structure instead of relying only on keyword search.

---

## What ContextForge Produces

Running a graph build creates three primary files inside the analyzed repository:

```text
contextforge-out/
├── graph.html
├── GRAPH_REPORT.md
└── graph.json
```

### `graph.html`

A standalone interactive visualization of the repository.

Use it to:

- Search for nodes
- Inspect neighboring components and relationships
- Filter architectural communities
- View source locations and confidence labels
- Explore the codebase visually

### `GRAPH_REPORT.md`

A human-readable overview of the repository, including:

- Major architectural communities
- Highly connected nodes
- Cross-community relationships
- Relationship-confidence counts
- Suggested questions to investigate

### `graph.json`

The complete portable, machine-readable knowledge graph.

Developers and external tools can query this artifact without rebuilding the graph or rereading the entire repository.

---

## How It Works

ContextForge processes a repository through a multi-stage pipeline:

```text
Files
  ↓
Detection
  ↓
Syntax-tree extraction
  ↓
Graph construction
  ↓
Relationship resolution
  ↓
Community detection
  ↓
Architectural analysis
  ↓
Reports and exports
```

### 1. File Detection

ContextForge scans the selected directory and collects supported source files.

It respects `.gitignore` and can also use a `.contextforgeignore` file for project-specific exclusions. Symlinks and paths outside the repository root are rejected.

### 2. Code Extraction

Source code is parsed locally using Tree-sitter. Python also has a higher-fidelity AST-based index for task-specific context compilation.

The portable graph extractor identifies structural elements such as:

- Files and modules
- Classes, interfaces, functions, and methods
- Imports
- Function calls
- Inheritance relationships
- Source locations and qualified names

Because code is parsed through its syntax tree, ContextForge can identify structural relationships that ordinary text search may miss. Static extraction is best effort: dynamic dispatch, runtime imports, and data flow are not treated as proven facts.

### 3. Graph Construction

All extracted information is merged into a NetworkX directed multigraph.

Each node contains information such as:

```json
{
  "id": "function:src/auth.py:authenticate_user",
  "label": "authenticate_user",
  "kind": "function",
  "qualname": "authenticate_user",
  "source_file": "src/auth.py",
  "source_location": "L42",
  "start_line": 42,
  "end_line": 58,
  "language": "python"
}
```

Relationships become graph edges:

```json
{
  "source": "function:src/routes.py:login",
  "target": "function:src/auth.py:authenticate_user",
  "relation": "calls",
  "confidence": "INFERRED"
}
```

### 4. Relationship Confidence

Every relationship includes a confidence label:

| Label | Meaning |
| --- | --- |
| `EXTRACTED` | The relationship is explicitly represented in the syntax tree |
| `INFERRED` | The relationship was resolved from surrounding names or structure |
| `AMBIGUOUS` | More than one plausible target exists |

This makes it possible to distinguish direct evidence from system-generated conclusions.

### 5. Community Detection

ContextForge groups strongly connected nodes into architectural communities.

The default `auto` mode uses Leiden when the optional dependency is installed and otherwise falls back to deterministic NetworkX modularity clustering. These communities often correspond to areas such as authentication, API routing, persistence, testing, or developer tooling.

Community detection is based on graph structure rather than embedding similarity.

### 6. Architectural Analysis

After building the graph, ContextForge identifies:

- Highly connected components
- Central services and shared utilities
- Cross-community dependencies
- Relationship-confidence distributions
- Paths between otherwise distant components

The results are written to the report and made available through graph queries.

### 7. Task-Specific Context Compilation

The portable graph is one interface to ContextForge. The project also maintains an incremental SQLite/FTS5 index for compiling evidence for a specific bug report or software task.

That pipeline combines:

- BM25 code and path retrieval
- Exact and fuzzy symbol search
- Deterministic local vector retrieval
- Bounded call/import graph expansion
- Related-test discovery
- Confidence-gated Git history
- One bounded query-evolution pass
- Explainable reranking
- Diversity-aware selection under a strict estimated-token budget

The result contains source ranges, tests, relationships, and relevant historical evidence, plus a trace explaining why each item was selected or rejected.

---

## Supported Inputs

The portable graph extractor currently loads 26 Tree-sitter grammar modes across 44 file extensions:

- Python
- JavaScript and JSX
- TypeScript and TSX
- Java and Groovy
- Go
- Rust
- C and C++
- C#
- Kotlin and Scala
- Ruby
- PHP
- Swift and Objective-C
- Bash and PowerShell
- Elixir
- Lua
- Zig
- Julia
- Verilog
- Fortran
- JSON

Python has the most complete retrieval and relationship support. Multi-language extraction uses shared structural queries, so relationship fidelity varies by grammar. Markdown, PDFs, images, Office documents, audio, and video are not ingested in the current release.

---

## Installation

ContextForge requires Python 3.11 or newer.

### Install from the Repository

```bash
git clone https://github.com/rustagiaaryan/contextforge.git
cd contextforge
uv tool install .
```

You can also install it with `pipx`:

```bash
pipx install .
```

Confirm that the CLI is available:

```bash
contextforge --help
```

To enable Leiden community detection, install the optional extra:

```bash
uv tool install '.[leiden]'
```

### Register the Coding-Agent Skill

ContextForge includes a reusable project-scoped agent skill for graph-first repository exploration. Install it into the repository an agent will work on:

```bash
contextforge skill install ./repository
```

This writes `.agents/skills/contextforge-graph/` inside that repository. Use `--overwrite` only when intentionally replacing an existing installation:

```bash
contextforge skill install ./repository --overwrite
```

---

## Quick Start

Build a graph for a repository:

```bash
contextforge graph build ./repository
```

ContextForge creates:

```text
repository/contextforge-out/
├── graph.html
├── GRAPH_REPORT.md
└── graph.json
```

Open the interactive graph on macOS:

```bash
open repository/contextforge-out/graph.html
```

On Linux:

```bash
xdg-open repository/contextforge-out/graph.html
```

To build the current directory instead:

```bash
contextforge graph build .
```

---

## Querying the Graph

Once a graph has been created, you can explore it without reprocessing the repository.

### Ask a Question

```bash
contextforge graph query contextforge-out/graph.json \
  --question "How does authentication work?"
```

Additional examples:

```bash
contextforge graph query contextforge-out/graph.json \
  --question "Where are database connections created?"
```

```bash
contextforge graph query contextforge-out/graph.json \
  --question "How does an HTTP request reach the service layer?" \
  --limit 15 --hops 2
```

The query anchors on fuzzy node-name matches and returns a bounded subgraph containing the nodes and relationships most relevant to the question. It is deterministic graph retrieval, not an LLM-generated answer.

### Explain a Component

```bash
contextforge graph explain contextforge-out/graph.json UserService
```

This returns information such as:

- Where the component is defined
- What community it belongs to
- What it calls or imports
- What depends on it
- Its surrounding relationships

### Trace a Path

```bash
contextforge graph path \
  contextforge-out/graph.json LoginRoute UserRepository
```

ContextForge finds a shortest static path between the two concepts and prints the relationships along that path. Add `--json` for machine-readable output.

---

## MCP Integration

ContextForge includes a standard-input/output MCP server that gives coding agents structured access to the persistent repository index and graph relationships.

Start it locally:

```bash
contextforge mcp
```

The server exposes eleven typed tools:

- `index_repository`
- `get_index_status`
- `search_symbols`
- `search_code`
- `get_symbol`
- `get_callers`
- `get_callees`
- `find_related_tests`
- `search_git_history`
- `expand_graph_neighbors`
- `compile_task_context`

Each tool takes an explicit repository path, and expensive graph operations are bounded.

### Example MCP Configuration

For a globally installed CLI:

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

For a source checkout managed by `uv`:

```json
{
  "mcpServers": {
    "contextforge": {
      "command": "uv",
      "args": [
        "--directory",
        "<path-to-contextforge>",
        "run",
        "contextforge",
        "mcp"
      ]
    }
  }
}
```

Restart the coding assistant after adding the configuration. Full tool schemas and client notes are in [docs/MCP.md](docs/MCP.md).

The current release supports local stdio transport. It does not expose an unauthenticated network server.

---

## Updating an Existing Index or Graph

The task-specific SQLite index is incremental. Running this command again reprocesses only changed files and reuses cached vectors for unchanged content:

```bash
contextforge index ./repository
```

Portable `graph.json` artifacts are currently rebuilt from the repository:

```bash
contextforge graph build ./repository
```

Incremental portable-graph updates, Git hooks, and cluster-only rebuilds are roadmap items rather than current CLI features.

---

## Common Commands

```bash
# Build portable graph artifacts
contextforge graph build ./repository

# Build with a specific clustering backend
contextforge graph build ./repository --cluster networkx

# Ask a deterministic graph question
contextforge graph query repository/contextforge-out/graph.json \
  --question "How does the API communicate with persistence?"

# Explain one component
contextforge graph explain repository/contextforge-out/graph.json DatabasePool

# Trace a relationship path
contextforge graph path repository/contextforge-out/graph.json APIHandler DatabasePool

# Install the project-scoped coding-agent skill
contextforge skill install ./repository

# Build or update the task-retrieval index
contextforge index ./repository
contextforge status ./repository

# Search the retrieval index
contextforge search ./repository \
  --task "mounted route prefix regression" --limit 20

# Compile a strict-budget evidence package
contextforge compile ./repository \
  --task-file issue.md --token-budget 8000 --format markdown

# Launch the real-output retrieval dashboard
contextforge dashboard ./repository --open

# Start the local stdio MCP server
contextforge mcp
```

---

## Ignoring Files

ContextForge respects the repository's existing `.gitignore`.

For additional exclusions, create a `.contextforgeignore` file:

```gitignore
node_modules/
dist/
build/
coverage/
*.generated.py
vendor/
```

The syntax follows `.gitignore`, including negation rules:

```gitignore
*
!src/
!src/**
```

This example indexes only files inside `src/`.

---

## Privacy

Source code is parsed locally using Tree-sitter and Python's AST.

For a source-code repository:

- Source files do not need to be sent to an external model
- No API key is required
- Graph construction, querying, clustering, and context compilation run locally
- The default vector provider uses deterministic feature hashing and downloads no model
- No vector database or external graph database is required

ContextForge parses target repositories but never imports or executes their code. Retrieved source can still contain prompt injection, so downstream agents should treat it as untrusted evidence. See [docs/SECURITY.md](docs/SECURITY.md) for the threat model.

---

## Using ContextForge as a Library

Build the portable graph pipeline directly from Python:

```python
from pathlib import Path

from contextforge.codegraph import map_repository

result = map_repository(Path("./repository"))

print(result.graph_json)
print(result.report_markdown)
print(result.graph_html)
```

Or compile task-specific evidence through the public API:

```python
from contextforge import ContextForge

engine = ContextForge.open("./repository")
engine.index()

result = engine.compile_context(
    task="Requests through mounted applications lose their route prefix.",
    token_budget=8_000,
)

print(result.to_markdown())
```

The graph pipeline is organized into independent stages:

```text
collect_files()
→ extract_file()
→ build_graph()
→ cluster_graph()
→ analyze_graph()
→ write_report() / export_graph()
```

Each stage communicates through typed Python models or NetworkX graphs, making individual parts easier to test and extend.

---

## Measured Evaluation

ContextForge includes a reproducible benchmark built from 12 pinned, merged bug-fix pull requests: four each from Click, HTTPX, and Typer. Each task checks out the repository immediately before the fix, uses the real pull-request title as the query, and treats Python files changed by the developer's patch as the answer key.

At an 8,000-token budget and K=10, the checked-in full-pipeline run measured:

| Metric | Result | What it means |
| --- | ---: | --- |
| Package hit rate | **11/12 (91.7%)** | At least one eventual fix file appeared somewhere in the final evidence package |
| Fix-file recall | **69.4%** | The package retrieved 69.4% of all Python files later changed by developers |
| Average evidence size | **5,742 tokens** | Average estimated size of the selected evidence package |
| Estimated source-context reduction | **96.8%** | Reduction from an average 193,838-token repository source baseline to the selected package |
| Budget compliance | **12/12** | Every package stayed at or below the requested 8,000-token estimate |

These are retrieval measurements, not code-generation accuracy, patch success, or proof that 91.7% of bugs can be fixed. The dataset is curated and small. The result file, exact definitions, ablations, limitations, and reproduction command are in [docs/EVALUATION.md](docs/EVALUATION.md) and [benchmarks/results/historical_patches.json](benchmarks/results/historical_patches.json).

Run the included fixture benchmark without network access:

```bash
contextforge evaluate \
  --dataset benchmarks/sample_tasks.jsonl \
  --token-budget 2000 --top-k 3 --ablations
```

The historical benchmark downloads pinned public repositories and is therefore opt-in:

```bash
contextforge evaluate-history \
  --manifest benchmarks/historical_patches.jsonl \
  --workspace .contextforge/historical-benchmark \
  --token-budget 8000 --top-k 10
```

---

## Development

Clone the repository and install the development dependencies:

```bash
git clone https://github.com/rustagiaaryan/contextforge.git
cd contextforge
uv sync --extra dev
```

Run formatting, linting, static analysis, and tests:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src/contextforge
uv run pytest -q
```

Run the CLI from the development environment:

```bash
uv run contextforge graph build .
```

---

## Project Structure

```text
contextforge/
├── src/contextforge/
│   ├── codegraph/
│   │   ├── detect.py
│   │   ├── extract.py
│   │   ├── build.py
│   │   ├── cluster.py
│   │   ├── analyze.py
│   │   ├── query.py
│   │   ├── report.py
│   │   ├── export.py
│   │   └── pipeline.py
│   ├── indexing/
│   ├── retrieval/
│   ├── routing/
│   ├── reranking/
│   ├── optimization/
│   ├── mcp/
│   ├── evaluation/
│   └── dashboard/
├── tests/
├── benchmarks/
├── docs/
├── pyproject.toml
└── README.md
```

| Area | Responsibility |
| --- | --- |
| `codegraph/` | Detects files, extracts structure, builds and queries portable graphs |
| `indexing/` | Builds the incremental SQLite source, graph, vector, and Git index |
| `retrieval/` | Finds lexical, semantic, structural, test, and historical candidates |
| `routing/` | Selects retrieval sources for each task |
| `reranking/` | Combines signals into explainable candidate scores |
| `optimization/` | Selects diverse evidence under the token budget |
| `mcp/` | Exposes typed local tools to coding agents |
| `evaluation/` | Runs baselines, ablations, and retrieval metrics |
| `dashboard/` | Visualizes real context-compilation traces |

---

## Current Limitations

- Python has the highest-fidelity retrieval index; other languages use the shared Tree-sitter graph extractor.
- Portable graph artifacts are rebuilt rather than incrementally patched.
- Leiden is optional; the default installation can use deterministic NetworkX clustering.
- Static calls and references are best effort for dynamic code. ContextForge does not yet perform control-flow or data-flow slicing.
- The local vector provider is deterministic feature hashing, not a trained embedding model.
- Natural-language graph queries use fuzzy anchors and bounded traversal; they do not generate prose answers with an LLM.
- Document, PDF, image, audio, and video ingestion is not implemented.
- The historical benchmark measures context retrieval, not downstream patch success or developer productivity.

---

## Design Provenance

ContextForge's graph-artifact workflow is informed by Graphify's public product concepts, alongside repository-retrieval and code-search research. ContextForge is an independent implementation with its own source, persistent retrieval engine, evidence compiler, benchmark, CLI, and documentation; no third-party benchmark result is presented as ContextForge work.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/DECISIONS.md](docs/DECISIONS.md), and [docs/GRAPH.md](docs/GRAPH.md) for implementation details.

---

## License

ContextForge is available under the [MIT License](LICENSE).
