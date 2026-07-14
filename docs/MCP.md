# Model Context Protocol

ContextForge exposes the same persistent index and compiler used by the Python API and CLI as a local stdio MCP server. The server parses repository text but never imports or executes indexed code.

## Tools

| Tool | Purpose |
| --- | --- |
| `index_repository` | Incrementally index source, graph, embeddings, and Git history |
| `get_index_status` | Inspect persistent counts and parse errors |
| `search_symbols` | Exact and fuzzy class/function/method/test search |
| `search_code` | Hybrid BM25 and local-embedding search |
| `get_symbol` | Fetch a full source unit and its incoming/outgoing edges |
| `get_callers` / `get_callees` | Traverse resolved call edges |
| `find_related_tests` | Discover likely validation code for an implementation symbol |
| `search_git_history` | Retrieve confidence-gated historical changes |
| `expand_graph_neighbors` | Perform capped, edge-filtered structural expansion |
| `compile_task_context` | Compile the strict-budget JSON or Markdown evidence package |

## Client configuration

From a source checkout, add a stdio server entry to a compatible coding client. Replace the placeholder with the checkout path; do not place credentials in this file.

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

Installed packages can use `"command": "contextforge", "args": ["mcp"]`. Each tool accepts an explicit repository path, so one server can work with multiple local repositories. Indexing only writes the ignored `.contextforge/` database beneath the selected repository.

