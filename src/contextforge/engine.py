"""Public ContextForge indexing and context-compilation engine."""

from __future__ import annotations

import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from contextforge.config import ContextForgeConfig
from contextforge.context import EvidenceItem, EvidencePackage, StageTiming
from contextforge.embeddings import LocalHashEmbeddingProvider
from contextforge.graph import GraphBuilder
from contextforge.indexing import RepositoryIndexer
from contextforge.models import EdgeType, IndexStats, NodeType
from contextforge.optimization import BudgetOptimizer
from contextforge.optimization.tokens import estimate_tokens
from contextforge.reranking import WeightedReranker
from contextforge.retrieval import (
    GitHistoryIndexer,
    GitHistoryRetriever,
    LexicalRetriever,
    QueryEvolution,
    RelatedTestRetriever,
    SemanticIndexer,
    SemanticRetriever,
    StructuralRetriever,
    SymbolRetriever,
)
from contextforge.retrieval.evolution import QueryEvolutionTrace
from contextforge.retrieval.history import CommitEvidence
from contextforge.retrieval.models import Candidate, RetrievalSource, merge_candidates
from contextforge.routing import AdaptiveRouter, RouteSource
from contextforge.storage import Database


class IndexReport(BaseModel):
    """Aggregate source, graph, semantic, and history indexing result."""

    model_config = ConfigDict(frozen=True)

    source: IndexStats
    graph_nodes: int = 0
    graph_edges: int = 0
    embeddings_generated: int = 0
    embeddings_cached: int = 0
    semantic_enabled: bool = True
    semantic_error: str | None = None
    git_available: bool = False
    commits_indexed: int = 0
    elapsed_ms: float = Field(ge=0.0)


class IndexStatus(BaseModel):
    """Current persistent index status for CLI and MCP clients."""

    model_config = ConfigDict(frozen=True)

    repository: str
    database_path: str
    indexed: bool
    files: int
    units: int
    graph_nodes: int
    graph_edges: int
    embeddings: int
    commits: int
    parse_errors: tuple[str, ...] = ()


class ContextForge:
    """Index a repository and compile task-specific evidence under a hard budget."""

    def __init__(self, repository: Path, config: ContextForgeConfig) -> None:
        self.repository = repository
        self.config = config
        self.database = Database(config.database_path(repository))
        self.embedding_provider = (
            LocalHashEmbeddingProvider(config.semantic_dimensions)
            if config.embedding_provider == "local"
            else None
        )

    @classmethod
    def open(
        cls, repository: str | Path, *, config: ContextForgeConfig | None = None
    ) -> ContextForge:
        """Open a local repository without executing its code."""
        root = Path(repository).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise NotADirectoryError(f"Repository path is not a directory: {root}")
        return cls(root, config or ContextForgeConfig.from_repository(root))

    def index(self) -> IndexReport:
        """Incrementally index source, rebuild the graph, cache embeddings, and index Git."""
        started = time.perf_counter()
        source = RepositoryIndexer(self.repository, self.database, config=self.config).index()
        graph_nodes, graph_edges = GraphBuilder(self.repository, self.database).build()
        semantic_generated = 0
        semantic_cached = 0
        semantic_enabled = self.embedding_provider is not None
        semantic_error: str | None = None
        if self.embedding_provider:
            semantic = SemanticIndexer(self.database, self.embedding_provider).index()
            semantic_generated = semantic.embedded_units
            semantic_cached = semantic.cached_units
            semantic_enabled = semantic.enabled
            semantic_error = semantic.error
        history = GitHistoryIndexer(
            self.repository,
            self.database,
            provider=self.embedding_provider,
        ).index()
        return IndexReport(
            source=source,
            graph_nodes=graph_nodes,
            graph_edges=graph_edges,
            embeddings_generated=semantic_generated,
            embeddings_cached=semantic_cached,
            semantic_enabled=semantic_enabled,
            semantic_error=semantic_error,
            git_available=history.available,
            commits_indexed=history.commits_indexed,
            elapsed_ms=(time.perf_counter() - started) * 1000,
        )

    def compile_context(self, *, task: str, token_budget: int = 8_000) -> EvidencePackage:
        """Compile ranked, explainable implementation and validation evidence."""
        if token_budget < 512:
            raise ValueError("token_budget must be at least 512")
        self.database.initialize()
        if not self.database.list_units(node_types=(NodeType.FILE,)):
            self.index()
        timings: list[StageTiming] = []

        started = time.perf_counter()
        route = AdaptiveRouter().route(task)
        timings.append(self._timing("routing", started, len(route.selected_sources)))
        if not route.retrieval_needed:
            package = EvidencePackage(
                task=task,
                repository=self.repository.name,
                token_budget=token_budget,
                estimated_tokens=0,
                routing=route,
                items=(),
                timings=tuple(timings),
            )
            package.estimated_tokens = estimate_tokens(package.to_markdown())
            return package

        started = time.perf_counter()
        initial_groups: list[list[Candidate]] = []
        if RouteSource.LEXICAL in route.selected_sources:
            initial_groups.append(LexicalRetriever(self.database).search(task, limit=40))
        if RouteSource.SYMBOL in route.selected_sources:
            initial_groups.append(SymbolRetriever(self.database).search(task, limit=25))
        semantic_enabled = self.embedding_provider is not None
        if RouteSource.SEMANTIC in route.selected_sources and self.embedding_provider:
            initial_groups.append(
                SemanticRetriever(self.database, self.embedding_provider).search(task, limit=35)
            )
        initial = merge_candidates(initial_groups)
        initial_ranked = WeightedReranker().rerank(initial, task=task, route=route)
        anchors = initial_ranked[:8]
        timings.append(self._timing("anchor_retrieval", started, len(initial)))

        started = time.perf_counter()
        structural: list[Candidate] = []
        structural_sources = {
            RouteSource.CALL_GRAPH,
            RouteSource.IMPORTS,
            RouteSource.INHERITANCE,
        }.intersection(route.selected_sources)
        if structural_sources:
            edge_types = {EdgeType.DEFINES, EdgeType.REFERENCES}
            if RouteSource.CALL_GRAPH in structural_sources:
                edge_types.add(EdgeType.CALLS)
            if RouteSource.IMPORTS in structural_sources:
                edge_types.add(EdgeType.IMPORTS)
            if RouteSource.INHERITANCE in structural_sources:
                edge_types.add(EdgeType.INHERITS)
            structural = StructuralRetriever(self.database).expand(
                anchors,
                edge_types=edge_types,
                max_depth=self.config.graph_max_depth,
                max_nodes=self.config.graph_max_nodes,
            )
        related_tests: list[Candidate] = []
        if RouteSource.RELATED_TESTS in route.selected_sources:
            related_tests = RelatedTestRetriever(self.database).find(
                [candidate.unit for candidate in anchors], task=task
            )
        timings.append(
            self._timing("structural_and_tests", started, len(structural) + len(related_tests))
        )

        started = time.perf_counter()
        evolution = QueryEvolution(self.database).evolve(task, initial_ranked)
        evolved_groups: list[list[Candidate]] = []
        if evolution.derived_concepts:
            evolved_groups.append(
                LexicalRetriever(self.database).search(evolution.evolved_query, limit=20)
            )
            evolved_groups.append(
                SymbolRetriever(self.database).search(evolution.evolved_query, limit=12)
            )
            if self.embedding_provider and RouteSource.SEMANTIC in route.selected_sources:
                evolved_groups.append(
                    SemanticRetriever(self.database, self.embedding_provider).search(
                        evolution.evolved_query, limit=20
                    )
                )
        evolved = merge_candidates(evolved_groups)
        initial_ids = {candidate.unit.unit_id for candidate in initial}
        added_ids = {candidate.unit.unit_id for candidate in evolved} - initial_ids
        for candidate in evolved:
            signal = max(candidate.source_scores.values(), default=0.0) * 0.7
            candidate.add_signal(
                RetrievalSource.QUERY_EVOLUTION,
                signal,
                "Found during the single bounded query-evolution pass.",
            )
        evolution = QueryEvolutionTrace(
            **evolution.model_dump(exclude={"added_candidate_count"}),
            added_candidate_count=len(added_ids),
        )
        timings.append(self._timing("query_evolution", started, len(evolved)))

        started = time.perf_counter()
        history_retriever = GitHistoryRetriever(self.database, provider=self.embedding_provider)
        history: tuple[CommitEvidence, ...] = ()
        hotspots: tuple[tuple[str, int], ...] = ()
        if RouteSource.GIT_HISTORY in route.selected_sources:
            history = tuple(
                history_retriever.search(
                    task,
                    anchor_paths={candidate.unit.path for candidate in anchors},
                    limit=5,
                )
            )
        if RouteSource.HOTSPOTS in route.selected_sources:
            hotspots = tuple(history_retriever.hotspots(limit=10))
        timings.append(self._timing("git_history", started, len(history)))

        started = time.perf_counter()
        all_candidates = merge_candidates([initial, structural, related_tests, evolved])
        ranked = WeightedReranker().rerank(all_candidates, task=task, route=route)
        timings.append(self._timing("reranking", started, len(ranked)))

        # Reserve the measured package trace and Git metadata before selecting source.
        skeleton = EvidencePackage(
            task=task,
            repository=self.repository.name,
            token_budget=token_budget,
            estimated_tokens=0,
            routing=route,
            items=(),
            relevant_commits=history,
            query_evolution=evolution,
            timings=tuple(timings),
            initial_anchor_ids=tuple(candidate.unit.unit_id for candidate in anchors),
            graph_expansion_count=len(structural),
            hotspot_files=hotspots,
            semantic_enabled=semantic_enabled,
        )
        reserve = estimate_tokens(skeleton.to_markdown()) + 32
        optimizer = BudgetOptimizer()
        started = time.perf_counter()
        optimized = optimizer.select(ranked, token_budget=max(0, token_budget - reserve))
        timings.append(self._timing("budget_optimization", started, len(optimized.selected)))
        decisions_by_id = {decision.unit_id: decision for decision in optimized.decisions}
        items = tuple(
            EvidenceItem.from_candidate(candidate, decisions_by_id[candidate.unit.unit_id])
            for candidate in optimized.selected
        )
        package = EvidencePackage(
            task=task,
            repository=self.repository.name,
            token_budget=token_budget,
            estimated_tokens=0,
            routing=route,
            items=items,
            relevant_commits=history,
            query_evolution=evolution,
            timings=tuple(timings),
            decisions=optimized.decisions,
            initial_anchor_ids=tuple(candidate.unit.unit_id for candidate in anchors),
            graph_expansion_count=len(structural),
            hotspot_files=hotspots,
            semantic_enabled=semantic_enabled,
        )
        self._enforce_render_budget(package)
        return package

    def get_index_status(self) -> IndexStatus:
        """Inspect the repository-local index without mutating repository source."""
        self.database.initialize()
        with self.database.connection() as connection:
            files = int(connection.execute("SELECT COUNT(*) FROM files").fetchone()[0])
            units = int(connection.execute("SELECT COUNT(*) FROM units").fetchone()[0])
            graph_nodes = int(connection.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0])
            graph_edges = int(connection.execute("SELECT COUNT(*) FROM graph_edges").fetchone()[0])
            embeddings = int(connection.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0])
            commits = int(connection.execute("SELECT COUNT(*) FROM commits").fetchone()[0])
            errors = tuple(
                f"{row['path']}: {row['parse_error']}"
                for row in connection.execute(
                    "SELECT path, parse_error FROM files "
                    "WHERE parse_error IS NOT NULL ORDER BY path"
                )
            )
        return IndexStatus(
            repository=str(self.repository),
            database_path=str(self.database.path),
            indexed=files > 0,
            files=files,
            units=units,
            graph_nodes=graph_nodes,
            graph_edges=graph_edges,
            embeddings=embeddings,
            commits=commits,
            parse_errors=errors,
        )

    def search_code(self, query: str, *, limit: int = 20) -> list[Candidate]:
        """Run hybrid lexical/semantic code search with unified ranking."""
        self._ensure_index()
        route = AdaptiveRouter().route(query)
        groups = [LexicalRetriever(self.database).search(query, limit=max(limit * 2, 20))]
        if self.embedding_provider:
            groups.append(
                SemanticRetriever(self.database, self.embedding_provider).search(
                    query, limit=max(limit * 2, 20)
                )
            )
        candidates = merge_candidates(groups)
        return WeightedReranker().rerank(candidates, task=query, route=route)[:limit]

    def search_symbols(self, query: str, *, limit: int = 20) -> list[Candidate]:
        """Search exact and fuzzy symbol names with explanations."""
        self._ensure_index()
        route = AdaptiveRouter().route(query)
        candidates = SymbolRetriever(self.database).search(query, limit=limit * 2)
        return WeightedReranker().rerank(candidates, task=query, route=route)[:limit]

    def _ensure_index(self) -> None:
        self.database.initialize()
        if not self.database.list_units(node_types=(NodeType.FILE,)):
            self.index()

    @staticmethod
    def _timing(stage: str, started: float, item_count: int) -> StageTiming:
        return StageTiming(
            stage=stage,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            item_count=item_count,
        )

    @staticmethod
    def _enforce_render_budget(package: EvidencePackage) -> None:
        """Remove lowest-scored blocks until rendered Markdown obeys the hard budget."""
        while True:
            package.estimated_tokens = estimate_tokens(package.to_markdown())
            if package.estimated_tokens <= package.token_budget or not package.items:
                break
            lowest = min(package.items, key=lambda item: (item.score, -item.estimated_tokens))
            package.items = tuple(item for item in package.items if item is not lowest)
        package.estimated_tokens = estimate_tokens(package.to_markdown())
