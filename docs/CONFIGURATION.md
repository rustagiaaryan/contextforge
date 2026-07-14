# Configuration

ContextForge works without configuration. For repository-specific limits, add `.contextforge.toml` at the selected repository root:

```toml
[contextforge]
database_dir = ".contextforge"
max_file_bytes = 2000000
graph_max_depth = 2
graph_max_nodes = 40
semantic_dimensions = 384
embedding_provider = "local"
```

Unknown fields and invalid ranges fail fast. Environment variables override the file: `CONTEXTFORGE_DB_DIR`, `CONTEXTFORGE_MAX_FILE_BYTES`, `CONTEXTFORGE_GRAPH_MAX_DEPTH`, `CONTEXTFORGE_GRAPH_MAX_NODES`, `CONTEXTFORGE_SEMANTIC_DIMENSIONS`, and `CONTEXTFORGE_EMBEDDING_PROVIDER`.

The only built-in provider is `local`, a deterministic signed feature-hashing baseline. Setting another provider name disables semantic retrieval without disabling lexical, symbol, graph, test, or Git retrieval. Custom applications can supply an implementation of the typed `EmbeddingProvider` protocol.

Keep configuration free of credentials. Optional provider credentials belong in environment variables and must never be written into evidence packages or committed files.

