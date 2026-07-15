# Graph-first repository workflow

ContextForge can produce a portable repository knowledge graph independently of its SQLite
context compiler. The workflow is local and deterministic:

```text
detect → Tree-sitter extract → resolve/build → cluster → analyze → report/export
```

Each stage accepts ordinary Python records or a NetworkX graph. The only generated state is written
beneath the selected repository's `contextforge-out/` directory.

## Build

```bash
contextforge graph build ./repository
```

Use `--cluster networkx` for the dependency-free deterministic community backend. `--cluster
leiden` requires the `leiden` optional dependency; `auto` tries Leiden when installed and otherwise
uses NetworkX modularity clustering.

The output contains:

- `graph.json`: the complete portable node/edge graph, metadata, confidence counts, communities,
  central concepts, and stage timings;
- `GRAPH_REPORT.md`: central nodes, subsystem summaries, cross-community relationships, and useful
  follow-up questions;
- `graph.html`: a standalone interactive SVG explorer with search, community filters, pan/zoom,
  and node relationship details.

## Query

Do not send the complete graph to an agent when a scoped query is sufficient:

```bash
contextforge graph query ./repository/contextforge-out/graph.json \
  --question "Where is authentication connected to request routing?" \
  --limit 25 --hops 1
```

The query uses RapidFuzz to locate up to three strong node anchors, then performs a bounded
NetworkX neighborhood expansion. This graph query path intentionally has no embedding model or
vector store; the separate `contextforge compile` pipeline still supports hybrid retrieval.

Trace and explain concepts directly:

```bash
contextforge graph path ./repository/contextforge-out/graph.json Router RequestHandler
contextforge graph explain ./repository/contextforge-out/graph.json Router
```

## Confidence

Every relationship exposes one of three labels:

- `EXTRACTED`: explicitly present in source, such as a definition or import statement;
- `INFERRED`: linked to a likely local target during deterministic name resolution;
- `AMBIGUOUS`: multiple local targets remain plausible and are retained for review.

Confidence describes extraction provenance, not runtime certainty. Dynamic dispatch, reflection,
generated code, and aliases can make a syntactically explicit relationship incomplete or
misleading.

## Language coverage

The default dependency set loads 26 Tree-sitter grammar entry points covering 44 extensions:
Python, JavaScript/JSX, TypeScript/TSX, Go, Rust, Java, Groovy, C, C++, Ruby, C#, Kotlin, Scala,
PHP, Swift, Lua, Zig, PowerShell, Elixir, Objective-C, Julia, Verilog, Fortran, Bash, and JSON.

The shared extractor recognizes common definition, import, inheritance, and call shapes. Python,
TypeScript, and Go have semantic fixture coverage. Other grammars have load/parse smoke coverage;
language-specialized extraction remains roadmap work and should not be described as equally precise.

## Agent skill

Install the bundled workflow into a target repository:

```bash
contextforge skill install ./repository
```

This writes `.agents/skills/contextforge-graph/SKILL.md` and its UI metadata. The skill directs an
agent to build or refresh the artifact, issue scoped graph queries, inspect referenced source, and
interpret confidence labels conservatively.
