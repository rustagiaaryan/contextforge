"""Deterministic upstream dependency and test impact analysis."""

from __future__ import annotations

import heapq
from collections.abc import Iterable
from pathlib import Path

from contextforge.graph import GraphQuery
from contextforge.graph.models import GraphEdge
from contextforge.impact.git_changes import ChangedRange, GitChangeReader
from contextforge.impact.models import (
    ImpactedSymbol,
    ImpactReport,
    ImpactSeed,
    ImpactStep,
    RiskLevel,
)
from contextforge.models import EdgeType, NodeType, SourceUnit
from contextforge.retrieval.tests import RelatedTestRetriever
from contextforge.storage import Database

_UPSTREAM_EDGES = {
    EdgeType.CALLS,
    EdgeType.REFERENCES,
    EdgeType.IMPORTS,
    EdgeType.INHERITS,
    EdgeType.TESTS,
}


class ImpactAnalyzer:
    """Find code and tests that may depend on an indexed symbol."""

    def __init__(self, repository: Path, database: Database) -> None:
        self.repository = repository.resolve(strict=True)
        self.database = database
        self.graph = GraphQuery(database)
        self.test_retriever = RelatedTestRetriever(database)

    def analyze_symbol(
        self,
        identifier: str,
        *,
        max_depth: int = 3,
        limit: int = 200,
    ) -> ImpactReport:
        """Analyze upstream dependents of one exact symbol identifier."""
        unit = self._resolve_symbol(identifier)
        return self.analyze_units(
            (unit,),
            target=identifier,
            mode="symbol",
            max_depth=max_depth,
            limit=limit,
        )

    def analyze_changes(
        self,
        *,
        base: str | None = None,
        max_depth: int = 3,
        limit: int = 200,
    ) -> ImpactReport:
        """Map local or branch changes to indexed symbols and their dependents."""
        changes = GitChangeReader(self.repository).read(base)
        all_units = self.database.list_units()
        units_by_path: dict[str, list[SourceUnit]] = {}
        for unit in all_units:
            units_by_path.setdefault(unit.path, []).append(unit)
        mapped: dict[str, SourceUnit] = {}
        unresolved: set[str] = set()
        for change in changes:
            mapped_unit = self._map_change(change, units_by_path.get(change.path, []))
            if mapped_unit is None:
                unresolved.add(change.path)
            else:
                mapped[mapped_unit.unit_id] = mapped_unit
        target = f"changes since {base}" if base else "working tree changes"
        return self.analyze_units(
            mapped.values(),
            target=target,
            mode="changes",
            max_depth=max_depth,
            limit=limit,
            unresolved=tuple(unresolved),
            changed_files=tuple(change.path for change in changes),
        )

    def analyze_units(
        self,
        units: Iterable[SourceUnit],
        *,
        target: str,
        mode: str,
        max_depth: int = 3,
        limit: int = 200,
        unresolved: tuple[str, ...] = (),
        changed_files: tuple[str, ...] = (),
    ) -> ImpactReport:
        """Analyze already-resolved units, including those mapped from a Git diff."""
        if max_depth not in range(1, 4):
            raise ValueError("max_depth must be between 1 and 3")
        if limit not in range(1, 201):
            raise ValueError("limit must be between 1 and 200")
        seed_units = tuple(sorted(set(units), key=lambda unit: unit.unit_id))
        seeds = tuple(self._seed(unit) for unit in seed_units)
        seed_ids = {unit.unit_id for unit in seed_units}
        reached, truncated = self._traverse(seed_ids, max_depth=max_depth, limit=limit)
        related_test_ids = {
            candidate.unit.unit_id
            for candidate in self.test_retriever.find(list(seed_units), limit=min(limit, 24))
        }
        impacted = tuple(
            symbol for symbol in reached if not symbol.is_test and symbol.unit_id not in seed_ids
        )
        related_tests = tuple(
            symbol
            for symbol in reached
            if symbol.is_test
            and self._is_test_case(symbol.unit_id)
            and (symbol.unit_id in related_test_ids or symbol.relationship_path)
        )
        impacted_files = tuple(sorted({symbol.path for symbol in impacted}))
        communities = tuple(
            sorted({symbol.community for symbol in impacted if symbol.community is not None})
        )
        risk_level, risk_reasons = self._classify_risk(
            seed_units,
            impacted,
            communities,
            truncated=truncated,
        )
        return ImpactReport(
            repository=str(self.repository),
            mode="changes" if mode == "changes" else "symbol",
            target=target,
            max_depth=max_depth,
            limit=limit,
            seeds=seeds,
            impacted=impacted,
            related_tests=related_tests,
            impacted_files=impacted_files,
            changed_files=tuple(sorted(set(changed_files))),
            communities=communities,
            unresolved=tuple(sorted(set(unresolved))),
            risk_level=risk_level,
            risk_reasons=risk_reasons,
            truncated=truncated,
        )

    def _is_test_case(self, unit_id: str) -> bool:
        unit = self.database.get_unit(unit_id)
        return bool(unit and unit.signature and unit.name.startswith("test"))

    def _resolve_symbol(self, identifier: str) -> SourceUnit:
        units = self.database.list_units()
        by_id = [unit for unit in units if unit.unit_id == identifier]
        if by_id:
            return by_id[0]
        by_qualname = [unit for unit in units if unit.qualname == identifier]
        if len(by_qualname) == 1:
            return by_qualname[0]
        by_name = [unit for unit in units if unit.name == identifier]
        matches = by_qualname or by_name
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise ValueError(f"Unknown symbol: {identifier}")
        choices = ", ".join(sorted(unit.qualname for unit in matches)[:10])
        raise ValueError(f"Ambiguous symbol '{identifier}'; choose one of: {choices}")

    @staticmethod
    def _map_change(change: ChangedRange, units: list[SourceUnit]) -> SourceUnit | None:
        if change.status == "deleted":
            return None
        by_id = {unit.unit_id: unit for unit in units}

        def depth(unit: SourceUnit) -> int:
            result = 0
            parent_id = unit.parent_id
            while parent_id and parent_id in by_id:
                result += 1
                parent_id = by_id[parent_id].parent_id
            return result

        overlapping = [
            unit
            for unit in units
            if unit.node_type not in {NodeType.FILE, NodeType.MODULE}
            and unit.start_line <= change.end_line
            and unit.end_line >= change.start_line
        ]
        if overlapping:
            return min(
                overlapping,
                key=lambda unit: (
                    unit.end_line - unit.start_line,
                    -depth(unit),
                    unit.unit_id,
                ),
            )
        return next((unit for unit in units if unit.node_type is NodeType.FILE), None)

    def _traverse(
        self,
        seed_ids: set[str],
        *,
        max_depth: int,
        limit: int,
    ) -> tuple[tuple[ImpactedSymbol, ...], bool]:
        queue: list[tuple[int, float, tuple[str, ...], str, tuple[GraphEdge, ...]]] = []
        for seed_id in sorted(seed_ids):
            heapq.heappush(queue, (0, -1.0, (seed_id,), seed_id, ()))
        best: dict[str, tuple[int, float, tuple[str, ...]]] = {
            seed_id: (0, 1.0, (seed_id,)) for seed_id in seed_ids
        }
        results: list[ImpactedSymbol] = []
        production_count = 0
        truncated = False
        while queue:
            distance, negative_confidence, path_ids, current_id, path = heapq.heappop(queue)
            confidence = -negative_confidence
            if best.get(current_id) != (distance, confidence, path_ids):
                continue
            if distance:
                unit = self.database.get_unit(current_id)
                if unit is not None and self._is_reportable(unit):
                    if not unit.is_test and production_count >= limit:
                        truncated = True
                        continue
                    results.append(self._impacted(unit, distance, confidence, path))
                    if not unit.is_test:
                        production_count += 1
            if distance >= max_depth:
                continue
            incoming, _ = self.graph.edges(current_id)
            for edge in incoming:
                if edge.edge_type not in _UPSTREAM_EDGES or edge.source_id in seed_ids:
                    continue
                unit = self.database.get_unit(edge.source_id)
                if unit is None:
                    continue
                next_distance = distance + 1
                next_confidence = min(confidence, edge.confidence)
                next_path_ids = (edge.source_id, *path_ids)
                previous = best.get(edge.source_id)
                candidate = (next_distance, next_confidence, next_path_ids)
                if previous is not None and not self._is_better(candidate, previous):
                    continue
                best[edge.source_id] = candidate
                heapq.heappush(
                    queue,
                    (
                        next_distance,
                        -next_confidence,
                        next_path_ids,
                        edge.source_id,
                        (edge, *path),
                    ),
                )
        results.sort(key=lambda item: (item.distance, -item.path_confidence, item.unit_id))
        return tuple(results), truncated

    @staticmethod
    def _is_reportable(unit: SourceUnit) -> bool:
        return unit.node_type in {
            NodeType.CLASS,
            NodeType.FUNCTION,
            NodeType.METHOD,
            NodeType.TEST,
        }

    @staticmethod
    def _is_better(
        candidate: tuple[int, float, tuple[str, ...]],
        previous: tuple[int, float, tuple[str, ...]],
    ) -> bool:
        return (candidate[0], -candidate[1], candidate[2]) < (
            previous[0],
            -previous[1],
            previous[2],
        )

    def _impacted(
        self,
        unit: SourceUnit,
        distance: int,
        confidence: float,
        path: tuple[GraphEdge, ...],
    ) -> ImpactedSymbol:
        node = self.graph.get_node(unit.unit_id)
        community = node.metadata.get("community") if node else None
        return ImpactedSymbol(
            **self._seed(unit).model_dump(),
            distance=distance,
            path_confidence=confidence,
            relationship_path=tuple(
                ImpactStep(
                    source_id=edge.source_id,
                    target_id=edge.target_id,
                    edge_type=edge.edge_type,
                    confidence=edge.confidence,
                )
                for edge in path
            ),
            is_test=unit.is_test,
            community=int(community) if isinstance(community, int) else None,
        )

    @staticmethod
    def _seed(unit: SourceUnit) -> ImpactSeed:
        return ImpactSeed(
            unit_id=unit.unit_id,
            qualname=unit.qualname,
            path=unit.path,
            start_line=unit.start_line,
            end_line=unit.end_line,
        )

    def _classify_risk(
        self,
        seeds: tuple[SourceUnit, ...],
        impacted: tuple[ImpactedSymbol, ...],
        communities: tuple[int, ...],
        *,
        truncated: bool,
    ) -> tuple[RiskLevel, tuple[str, ...]]:
        files = {symbol.path for symbol in impacted}
        direct_dependents = sum(symbol.distance == 1 for symbol in impacted)
        public_seed = any(not unit.name.startswith("_") for unit in seeds)
        reasons = [
            f"{len(impacted)} impacted production symbols",
            f"{len(files)} impacted production files",
            f"{len(communities)} dependency communities",
        ]
        if truncated:
            reasons.append("result limit reached; additional dependents exist")
        if public_seed and direct_dependents >= 5:
            reasons.append(f"public seed has {direct_dependents} direct dependents")
        community_high = len(impacted) >= 8 and len(communities) > 2
        high = (
            len(impacted) > 15
            or len(files) > 5
            or community_high
            or (public_seed and direct_dependents >= 5)
            or truncated
        )
        community_medium = len(impacted) >= 4 and len(communities) >= 2
        medium = len(impacted) >= 4 or len(files) >= 2 or community_medium
        return (RiskLevel.HIGH if high else RiskLevel.MEDIUM if medium else RiskLevel.LOW), tuple(
            reasons
        )
