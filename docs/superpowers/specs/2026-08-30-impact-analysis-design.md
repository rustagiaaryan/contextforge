# Change Impact Analysis Design

## Objective

Add deterministic blast-radius analysis to ContextForge so developers and coding agents can
understand what may be affected before changing a symbol or after modifying a working tree.

The first release covers the existing high-fidelity Python index. It reuses ContextForge's stored
symbols, call/import/reference graph, related-test discovery, Git metadata, and community labels.
It does not claim runtime certainty or attempt to edit source code.

## User workflows

### Symbol impact

```bash
contextforge impact ./repository --symbol app.services.UserService.save --depth 3
```

The command resolves a symbol, traverses incoming dependency edges, locates related tests, and
returns a grouped impact report. Human-readable output is the default; `--json` returns the stable
schema used by MCP.

### Working-tree impact

```bash
contextforge changes ./repository
contextforge changes ./repository --base main
```

The command reads changed line ranges from Git without executing repository code. It maps each
range to the narrowest indexed source units, analyzes the combined upstream neighborhood, and
reports files that changed but could not be mapped to indexed symbols.

### MCP

Two typed tools expose the same engine:

- `analyze_symbol_impact`
- `analyze_change_impact`

Both tools accept explicit repository paths and use the same depth and node caps as the CLI.

## Result model

An impact report contains:

- requested target or Git comparison;
- resolved seed symbols and changed files;
- impacted symbols grouped by distance from the seeds;
- impacted production files and likely related tests;
- crossed architectural communities;
- edge types and confidence labels that justify every result;
- unresolved changed files or identifiers;
- a deterministic risk level and explanation;
- truncation metadata when traversal reaches configured limits.

Each impacted symbol retains its stable unit ID, qualified name, path, source range, graph distance,
relationship path, confidence, and whether it is a test.

## Traversal and scoring

Impact traversal begins at one or more resolved source units and walks incoming `CALLS`,
`REFERENCES`, `IMPORTS`, `INHERITS`, and `TESTS` relationships. Incoming edges answer the blast-
radius question: what currently depends on the target?

The traversal is breadth-first and deterministic. It is capped at depth 3 and 200 returned symbols.
When multiple paths reach the same symbol, ContextForge keeps the path with the shortest distance,
then the strongest minimum edge confidence, then the lexicographically smallest stable path.

Confidence weights remain consistent with the existing graph:

- extracted: `1.0`;
- inferred: `0.72`;
- ambiguous: `0.4`.

Related tests are added through the existing multi-signal test retriever, but are identified as
validation evidence rather than mixed silently into production impact.

## Risk classification

Risk is an explainable heuristic, not a prediction of failure:

- `LOW`: at most 3 impacted symbols, one production file, and one community;
- `MEDIUM`: 4–15 symbols, 2–5 production files, or 2 communities;
- `HIGH`: more than 15 symbols, more than 5 production files, more than 2 communities, any public
  class/function with at least 5 direct dependents, or a truncated traversal.

The report lists the exact thresholds that caused the classification. Tests do not raise risk by
themselves; their presence is reported as validation coverage.

## Git change mapping

The Git adapter uses bounded, non-shell subprocess calls:

- no base: compare the working tree and index to `HEAD`;
- `--base REF`: compare `REF...HEAD`, then include uncommitted changes;
- parse zero-context unified diff hunk headers into changed line ranges;
- handle added, deleted, and renamed paths;
- map each range to the narrowest overlapping indexed unit;
- fall back to the file unit when no symbol overlaps.

Invalid revisions and non-Git repositories return concise errors. Deleted files remain in the
changed-file list but cannot become graph seeds unless an indexed rename target exists.

## Components

### `contextforge/impact/models.py`

Typed Pydantic models for seeds, relationship steps, impacted symbols, risk reasons, and the final
report. JSON produced by CLI and MCP comes from these models.

### `contextforge/impact/analyzer.py`

Resolves source units, performs deterministic upstream traversal, invokes related-test discovery,
computes community/file summaries, and classifies risk.

### `contextforge/impact/git_changes.py`

Reads bounded Git diffs and maps changed ranges to indexed units. It contains no graph traversal or
presentation logic.

### CLI and MCP adapters

`contextforge impact` and `contextforge changes` format reports from the analyzer. MCP tools return
the same models as JSON-compatible dictionaries. No logic is duplicated in either adapter.

## Error handling and limits

- Unknown or ambiguous symbols return candidate matches instead of choosing silently.
- Depth is restricted to `1..3`; result limits to `1..200`.
- Indexes are created automatically when missing and refreshed explicitly through the existing
  indexing command.
- Git commands disable prompts and use argument arrays without a shell.
- Reports state when results were truncated or graph confidence is below extracted evidence.

## Testing

Tests use controlled repositories with real Git history and source relationships.

1. Symbol impact returns direct and transitive callers in distance order.
2. Multiple paths keep the deterministic strongest shortest explanation.
3. Related tests are separated from production impact.
4. Risk thresholds produce LOW, MEDIUM, and HIGH with explicit reasons.
5. Working-tree, staged, committed-range, rename, and deletion diffs map correctly.
6. Unknown symbols, ambiguous symbols, invalid revisions, and non-Git repositories fail clearly.
7. CLI JSON matches the Pydantic schema.
8. A real stdio MCP session discovers and invokes both tools.
9. Existing retrieval, graph, benchmark, and MCP tests remain green.

## Follow-up milestones

After impact analysis ships independently:

1. add a PageRank-based repository map that selects signatures under a strict token budget;
2. expose the map through CLI and an MCP resource;
3. add graph staleness reporting and an opt-in debounced watch command;
4. highlight impact paths and risk groups in the interactive graph.

Each follow-up receives its own design and testable commit series rather than expanding this
milestone's interface.
