# Change Impact Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic symbol and Git-change blast-radius reports through Python, CLI, and MCP.

**Architecture:** Persist stable community labels during graph indexing, then build a read-only impact analyzer over the existing SQLite graph. A separate Git adapter converts zero-context diffs into indexed symbol seeds; CLI and MCP remain thin adapters over the same Pydantic reports.

**Tech Stack:** Python 3.11+, Pydantic 2, SQLite, NetworkX, Typer, FastMCP, pytest

**Spec:** `docs/superpowers/specs/2026-08-30-impact-analysis-design.md`

## Global Constraints

- Analyze repository source without importing or executing it.
- Keep symbol depth in `1..3` and returned graph symbols in `1..200`.
- Use subprocess argument arrays with `shell=False` for every Git command.
- Preserve deterministic ordering and explanations in JSON output.
- Treat risk as an explainable heuristic, never a failure prediction.
- Keep the default workflow local and keyless.

---

### Task 1: Persist deterministic graph communities

**Files:**
- Modify: `src/contextforge/graph/builder.py`
- Modify: `tests/test_graph.py`

**Interfaces:**
- Consumes: the completed `graph_nodes` and `graph_edges` tables in `GraphBuilder.build()`.
- Produces: integer `metadata["community"]` on every `GraphNode`, stable for identical graphs.

- [x] **Step 1: Write failing graph-community tests**

Add a test that builds the fixture graph twice and asserts every node has an integer community,
at least one community contains multiple nodes, and the complete node-to-community mapping is
identical across rebuilds:

```python
def test_graph_assigns_stable_dependency_communities(tmp_path: Path) -> None:
    database, graph = _graph(tmp_path)
    first = _community_map(database)
    GraphBuilder(tmp_path / "repository", database).build()
    second = _community_map(database)

    assert first == second
    assert all(isinstance(value, int) for value in first.values())
    assert len(set(first.values())) < len(first)
```

- [x] **Step 2: Run the test and verify the missing metadata failure**

Run: `uv run pytest tests/test_graph.py::test_graph_assigns_stable_dependency_communities -q`

Expected: FAIL because graph node metadata does not contain `community`.

- [x] **Step 3: Implement weighted deterministic community assignment**

Add `_assign_communities(connection)` to `GraphBuilder`. Load graph nodes and non-containment edges
into an undirected `networkx.Graph`, combine repeated edge confidence as weight, run
`greedy_modularity_communities`, sort groups by `(-len(group), min(group))`, give isolated nodes
singleton groups, and update each row's JSON metadata without removing existing keys.

```python
metadata = json.loads(str(row["metadata_json"]))
metadata["community"] = community_id
connection.execute(
    "UPDATE graph_nodes SET metadata_json = ? WHERE node_id = ?",
    (json.dumps(metadata, sort_keys=True), node_id),
)
```

- [x] **Step 4: Run graph tests**

Run: `uv run pytest tests/test_graph.py -q`

Expected: all graph tests PASS.

- [x] **Step 5: Commit and push**

```bash
git add src/contextforge/graph/builder.py tests/test_graph.py
git commit -m "feat(graph): persist stable dependency communities"
git push origin main
```

---

### Task 2: Define the stable impact report schema

**Files:**
- Create: `src/contextforge/impact/__init__.py`
- Create: `src/contextforge/impact/models.py`
- Create: `tests/test_impact_models.py`

**Interfaces:**
- Produces: `RiskLevel`, `ImpactStep`, `ImpactSeed`, `ImpactedSymbol`, `ImpactReport`.
- Consumers: analyzer, Git adapter, CLI, MCP.

- [x] **Step 1: Write failing serialization and validation tests**

Construct a report and assert that `model_dump(mode="json")` contains lowercase risk values,
relationship enum values, sorted file/community summaries, and immutable tuple fields. Also assert
Pydantic rejects distance zero, confidence above one, depth above three, and negative limits.

```python
def test_impact_report_serializes_stable_public_schema() -> None:
    report = ImpactReport(
        repository="sample",
        mode="symbol",
        target="app.routing.Mount.resolve",
        max_depth=3,
        limit=200,
        seeds=(ImpactSeed(...),),
        impacted=(ImpactedSymbol(...),),
        related_tests=(),
        impacted_files=("app/routing.py",),
        changed_files=(),
        communities=(0,),
        unresolved=(),
        risk_level=RiskLevel.LOW,
        risk_reasons=("1 impacted symbol",),
        truncated=False,
    )
    assert report.model_dump(mode="json")["risk_level"] == "low"
```

- [x] **Step 2: Run the model test and verify import failure**

Run: `uv run pytest tests/test_impact_models.py -q`

Expected: FAIL because `contextforge.impact` does not exist.

- [x] **Step 3: Implement frozen Pydantic models**

Use `ConfigDict(frozen=True)` and these public fields:

```python
class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class ImpactStep(BaseModel):
    source_id: str
    target_id: str
    edge_type: EdgeType
    confidence: float = Field(ge=0.0, le=1.0)

class ImpactSeed(BaseModel):
    unit_id: str
    qualname: str
    path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)

class ImpactedSymbol(ImpactSeed):
    distance: int = Field(ge=1, le=3)
    path_confidence: float = Field(ge=0.0, le=1.0)
    relationship_path: tuple[ImpactStep, ...]
    is_test: bool = False
    community: int | None = None

class ImpactReport(BaseModel):
    repository: str
    mode: Literal["symbol", "changes"]
    target: str
    max_depth: int = Field(ge=1, le=3)
    limit: int = Field(ge=1, le=200)
    seeds: tuple[ImpactSeed, ...]
    impacted: tuple[ImpactedSymbol, ...]
    related_tests: tuple[ImpactedSymbol, ...]
    impacted_files: tuple[str, ...]
    changed_files: tuple[str, ...]
    communities: tuple[int, ...]
    unresolved: tuple[str, ...]
    risk_level: RiskLevel
    risk_reasons: tuple[str, ...]
    truncated: bool
```

- [x] **Step 4: Run model tests**

Run: `uv run pytest tests/test_impact_models.py -q`

Expected: PASS.

- [x] **Step 5: Commit and push**

```bash
git add src/contextforge/impact tests/test_impact_models.py
git commit -m "feat(impact): define explainable impact report models"
git push origin main
```

---

### Task 3: Implement symbol resolution and upstream impact traversal

**Files:**
- Create: `src/contextforge/impact/analyzer.py`
- Modify: `src/contextforge/impact/__init__.py`
- Create: `tests/test_impact_analyzer.py`

**Interfaces:**
- Consumes: `Database`, `GraphQuery`, `RelatedTestRetriever`, symbol identifier.
- Produces: `ImpactAnalyzer(repository: Path, database: Database)`.
- Produces: `ImpactAnalyzer.analyze_symbol(identifier, *, max_depth=3, limit=200) -> ImpactReport`.
- Produces: `ImpactAnalyzer.analyze_units(units, *, target, mode, max_depth, limit, unresolved=()) -> ImpactReport` for the Git adapter.

- [x] **Step 1: Write failing direct/transitive impact test**

Copy the sample fixture, index it, then analyze `app.utils.join_path`. Assert `Mount.resolve` is
distance 1, `dispatch` is distance 2, the relationship steps are `CALLS`, path confidence is
non-increasing, and the route test appears only in `related_tests`.

- [x] **Step 2: Verify the analyzer test fails because the class is missing**

Run: `uv run pytest tests/test_impact_analyzer.py::test_symbol_impact_finds_callers_and_tests -q`

Expected: FAIL importing `ImpactAnalyzer`.

- [x] **Step 3: Implement exact symbol resolution**

Resolution order is stable ID, exact qualified name, then unique exact short name. Zero matches raise
`ValueError("Unknown symbol: ...")`; multiple matches raise a message listing at most ten sorted
qualified names. Do not use fuzzy matching to choose an impact seed.

- [x] **Step 4: Implement strongest-shortest upstream traversal**

Use a heap keyed by `(distance, -minimum_confidence, tuple(path_node_ids))`. Traverse incoming
`CALLS`, `REFERENCES`, `IMPORTS`, `INHERITS`, and `TESTS` edges. Test units are collected but not
enqueued as production impact. For equal-distance alternatives, retain the path with the greater
minimum edge confidence, then the lexicographically smaller path. Stop expanding at `max_depth` and
set `truncated=True` when another qualifying unseen node exists after `limit` results.

- [x] **Step 5: Add risk classification tests before implementation**

Test LOW for the small fixture, MEDIUM for four synthetic dependents/two files, and HIGH for a
public function with five direct dependents or a truncated result. Assert exact reason strings,
not merely enum values.

- [x] **Step 6: Implement `_classify_risk`**

Calculate production symbol count, distinct production paths, crossed communities, direct dependent
count, seed visibility (`name.startswith("_")` means private), and truncation. Return the highest
triggered level and sorted reasons matching the approved thresholds.

- [x] **Step 7: Add deterministic alternative-path test**

Insert two same-length graph paths to one dependent with confidence minima `0.4` and `0.72`. Assert
the report keeps the `0.72` path. Rebuild and re-run to verify identical JSON.

- [x] **Step 8: Run analyzer and graph tests**

Run: `uv run pytest tests/test_impact_analyzer.py tests/test_graph.py -q`

Expected: PASS.

- [x] **Step 9: Commit and push**

```bash
git add src/contextforge/impact tests/test_impact_analyzer.py
git commit -m "feat(impact): analyze symbol blast radius"
git push origin main
```

---

### Task 4: Map Git changes to indexed symbols

**Files:**
- Create: `src/contextforge/impact/git_changes.py`
- Modify: `src/contextforge/impact/analyzer.py`
- Create: `tests/test_change_impact.py`

**Interfaces:**
- Produces: `ChangedRange(path: str, start_line: int, end_line: int, status: str, old_path: str | None)`.
- Produces: `GitChangeReader(repository).read(base: str | None = None) -> tuple[ChangedRange, ...]`.
- Produces: `ImpactAnalyzer.analyze_changes(*, base=None, max_depth=3, limit=200) -> ImpactReport`.

- [x] **Step 1: Write a failing zero-context diff parser test**

Provide unified diff text containing modified, added, deleted, and renamed files. Assert parsed new-
side line ranges, status values, and `old_path` for renames. Deleted files have line range `0..0`.

- [x] **Step 2: Verify the parser test fails because the module is missing**

Run: `uv run pytest tests/test_change_impact.py::test_parse_diff_tracks_ranges_and_renames -q`

Expected: FAIL importing `GitChangeReader`.

- [x] **Step 3: Implement the bounded Git reader**

Set `GIT_TERMINAL_PROMPT=0`, `GIT_OPTIONAL_LOCKS=0`, and run with `check=True`, `capture_output=True`,
`text=True`, `timeout=30`. For no base run `git diff --relative --unified=0 --find-renames HEAD --`.
For a base combine `git diff BASE...HEAD` with `git diff HEAD`. Add untracked files from
`git ls-files --others --exclude-standard -z` as full-file ranges. Deduplicate exact ranges.

- [x] **Step 4: Add failing real-repository mapping tests**

Create a Git fixture with committed routing code, then separately modify a function body, stage a
test, add an untracked module, rename a file, delete a file, and compare a feature commit to `main`.
Assert changed ranges map to the narrowest overlapping source unit and unresolved deleted paths are
retained.

- [x] **Step 5: Implement range-to-unit mapping**

For each range, load units with the same path. Select overlapping non-file units sorted by smallest
span, deepest parent chain, then stable ID. Fall back to the file unit. Combine unique seeds through
`analyze_units`; deleted/unmapped paths go into `unresolved`.

- [x] **Step 6: Add invalid-repository and invalid-revision tests**

Assert concise `ValueError` messages include `not a Git repository` and `invalid Git revision`
without leaking full subprocess environment or stack traces through CLI adapters.

- [x] **Step 7: Run Git impact tests**

Run: `uv run pytest tests/test_change_impact.py tests/test_history.py -q`

Expected: PASS.

- [x] **Step 8: Commit and push**

```bash
git add src/contextforge/impact tests/test_change_impact.py
git commit -m "feat(impact): map Git changes to affected symbols"
git push origin main
```

---

### Task 5: Expose impact analysis through the Python API and CLI

**Files:**
- Modify: `src/contextforge/engine.py`
- Modify: `src/contextforge/cli.py`
- Modify: `tests/test_engine.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Produces: `ContextForge.analyze_impact(identifier, *, max_depth=3, limit=200) -> ImpactReport`.
- Produces: `ContextForge.analyze_changes(*, base=None, max_depth=3, limit=200) -> ImpactReport`.
- Produces: `contextforge impact REPOSITORY --symbol IDENTIFIER [--depth N] [--limit N] [--json]`.
- Produces: `contextforge changes REPOSITORY [--base REF] [--depth N] [--limit N] [--json]`.

- [x] **Step 1: Write failing engine API tests**

Assert both methods auto-create a missing index and return the same schema as direct analyzer calls.

- [x] **Step 2: Run the engine tests and verify missing methods**

Run: `uv run pytest tests/test_engine.py -q`

Expected: FAIL with missing `analyze_impact` / `analyze_changes` attributes.

- [x] **Step 3: Add minimal engine adapters**

Call `_ensure_index()`, instantiate `ImpactAnalyzer(self.repository, self.database)`, and return its
report. Keep Git and traversal logic out of `engine.py`.

- [x] **Step 4: Write failing CLI JSON and human-output tests**

Assert `--json` parses into an `ImpactReport`; human output contains the risk level, target, impacted
files, distance-grouped symbols, related tests, and truncation warning when applicable. Assert
invalid symbols and revisions exit nonzero with concise messages.

- [x] **Step 5: Implement the Typer commands and one shared renderer**

Use Typer bounds (`min=1`, `max=3/200`). `_render_impact_report(report)` creates Rich summary and
symbol tables. JSON output is `report.model_dump_json(indent=2)`.

- [x] **Step 6: Run API and CLI tests**

Run: `uv run pytest tests/test_engine.py tests/test_cli.py -q`

Expected: PASS.

- [x] **Step 7: Commit and push**

```bash
git add src/contextforge/engine.py src/contextforge/cli.py tests/test_engine.py tests/test_cli.py
git commit -m "feat(cli): add symbol and change impact commands"
git push origin main
```

---

### Task 6: Add typed MCP impact tools

**Files:**
- Modify: `src/contextforge/mcp/server.py`
- Modify: `tests/test_mcp.py`
- Modify: `docs/MCP.md`

**Interfaces:**
- Produces: `analyze_symbol_impact(repository, identifier, max_depth=3, limit=200)`.
- Produces: `analyze_change_impact(repository, base=None, max_depth=3, limit=200)`.

- [ ] **Step 1: Extend the MCP surface test first**

Add both tool names to the exact registered-tool set and real stdio call list. Assert returned
structured content includes `risk_level`, `seeds`, and `impacted`.

- [ ] **Step 2: Run MCP tests and verify discovery failure**

Run: `uv run pytest tests/test_mcp.py -q`

Expected: FAIL because the two tools are not registered.

- [ ] **Step 3: Implement thin typed MCP adapters**

Clamp depth/limit to approved bounds, call the engine methods, and return
`report.model_dump(mode="json")`. Tool docstrings must describe upstream impact, static-analysis
limits, and whether the call reads Git state.

- [ ] **Step 4: Update MCP documentation**

Add both tools to the table with concise purposes and show one example prompt for pre-change impact
and one for working-tree review.

- [ ] **Step 5: Run the real stdio integration test**

Run: `uv run pytest tests/test_mcp.py -q`

Expected: PASS with all 13 tools discovered and called through a subprocess session.

- [ ] **Step 6: Commit and push**

```bash
git add src/contextforge/mcp/server.py tests/test_mcp.py docs/MCP.md
git commit -m "feat(mcp): expose change impact analysis"
git push origin main
```

---

### Task 7: Document and validate the complete milestone

**Files:**
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/DEMO.md`
- Modify: `src/contextforge/bundled_skills/contextforge-graph/SKILL.md`
- Modify: `tests/test_package.py`

**Interfaces:**
- Documents the exact CLI/MCP commands and their static-analysis limits.
- Keeps the packaged graph skill aligned with the public tool surface.

- [ ] **Step 1: Add a package/documentation contract test**

Assert the installed wheel includes the impact package and bundled skill, and that README command
examples use existing command names. Keep the test behavioral: import `ImpactAnalyzer`, invoke CLI
`--help`, and install the skill rather than searching prose implementation details.

- [ ] **Step 2: Run the contract test and verify the bundled workflow is incomplete**

Run: `uv run pytest tests/test_package.py -q`

Expected: FAIL until the skill and public command expectations are updated.

- [ ] **Step 3: Update concise public documentation**

Add one short "Check the blast radius" README section, update the architecture data flow, add a
reproducible demo command, and teach the bundled skill to call impact analysis before recommending
cross-file changes. Do not add unmeasured performance or correctness claims.

- [ ] **Step 4: Run all local quality gates**

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src/contextforge
uv run pytest -q
uv build
```

Expected: formatting clean, no lint/type errors, all tests pass, wheel and sdist build successfully.

- [ ] **Step 5: Run end-to-end commands on the sample repository**

```bash
uv run contextforge impact tests/fixtures/sample_repo \
  --symbol app.utils.join_path --depth 3 --json

uv run contextforge changes . --base HEAD~1 --json
```

Expected: valid impact JSON, bounded results, explicit risk reasons, and no target-code execution.

- [ ] **Step 6: Audit repository presentation**

Run scans for machine-specific paths, credentials, forbidden comparison names, generated indexes,
and stale README commands. Confirm `git diff --check` succeeds.

- [ ] **Step 7: Commit and push**

```bash
git add README.md docs src/contextforge/bundled_skills tests/test_package.py
git commit -m "docs: add the change impact workflow"
git push origin main
```

- [ ] **Step 8: Verify CI and repository state**

Run `gh run watch --exit-status` for the pushed commit, then verify `HEAD == origin/main` and the
working tree is clean.
