# Demo

The reproducible demo indexes the checked-in Python fixture, compiles evidence for a cross-file routing bug, and opens the local Repository Observatory. The dashboard consumes the same `EvidencePackage` and SQLite graph as the Python, CLI, and MCP interfaces; it contains no mock retrieval data.

## Run the demo

```bash
uv sync --extra dev
uv run contextforge index tests/fixtures/sample_repo
uv run contextforge compile tests/fixtures/sample_repo \
  --task "Requests through mounted applications lose their route prefix." \
  --token-budget 1600 --format markdown
uv run contextforge dashboard tests/fixtures/sample_repo --open
```

Open `http://127.0.0.1:8765` if the browser does not open automatically. Submit the prefilled task to inspect:

- the adaptive source route and bounded evolved concepts;
- initial anchors and selected nodes on the real knowledge graph;
- every reranked candidate with its selection or rejection reason;
- strict token allocation and the final source ranges;
- deliberately selected regression tests, gated Git memory, and measured stage latency.

## Verified smoke output

The dashboard smoke check on the included task returned 9 selected items from 13 considered candidates, used 1,539 of 1,600 estimated tokens, classified the task as `cross_file_bug`, and overlaid all 9 selected nodes on the graph. Values vary slightly when repository Git history changes; no value is hard-coded in the interface.

The API backing the visual can also be inspected at `/api/docs`, `/api/status`, `/api/compile`, and `/api/graph`.

## Graph-first multi-language demo

```bash
uv run contextforge graph build tests/fixtures/multilang_repo --cluster networkx
uv run contextforge graph query \
  tests/fixtures/multilang_repo/contextforge-out/graph.json \
  --question "How does Mount reach join_path?"
uv run contextforge graph path \
  tests/fixtures/multilang_repo/contextforge-out/graph.json Mount join_path
open tests/fixtures/multilang_repo/contextforge-out/graph.html
```

The fixture contains Python, TypeScript, and Go. The graph and report are generated from those real
files; the interactive HTML is not a mock or separate data source.
