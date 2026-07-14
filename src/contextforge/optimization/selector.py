"""Diversity-aware context optimization under a strict source-token budget."""

from __future__ import annotations

import math
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from contextforge.models import NodeType
from contextforge.optimization.tokens import estimate_tokens
from contextforge.retrieval.models import Candidate, RetrievalSource
from contextforge.retrieval.text import query_terms


class SelectionDecision(BaseModel):
    """Explain why a reranked candidate was selected or rejected."""

    model_config = ConfigDict(frozen=True)

    unit_id: str
    file: str
    symbol: str
    score: float
    estimated_tokens: int
    selected: bool
    reason: str
    retrieved_by: tuple[RetrievalSource, ...]
    marginal_utility: float


@dataclass(frozen=True)
class OptimizationResult:
    """Selected candidates and the complete decision audit."""

    selected: tuple[Candidate, ...]
    decisions: tuple[SelectionDecision, ...]
    token_cost: int


def candidate_render_cost(candidate: Candidate) -> int:
    """Estimate the candidate's Markdown evidence block, including metadata."""
    header = (
        f"### {candidate.unit.qualname}\n"
        f"{candidate.unit.path}:{candidate.unit.start_line}-{candidate.unit.end_line}\n"
        f"score {candidate.score:.3f}; sources "
        f"{', '.join(source.value for source in candidate.retrieved_by)}\n"
        f"{' '.join(candidate.reasons[:3])}\n```{candidate.unit.language}\n\n```\n"
    )
    return estimate_tokens(header) + estimate_tokens(candidate.unit.content)


class BudgetOptimizer:
    """Greedy submodular-style selection balancing relevance, coverage, and cost."""

    def __init__(self, *, redundancy_penalty: bool = True) -> None:
        self.redundancy_penalty = redundancy_penalty

    def select(self, candidates: list[Candidate], *, token_budget: int) -> OptimizationResult:
        """Select whole source ranges without exceeding *token_budget*."""
        if token_budget <= 0 or not candidates:
            return OptimizationResult((), (), 0)
        remaining = list(candidates)
        selected: list[Candidate] = []
        costs = {
            candidate.unit.unit_id: candidate_render_cost(candidate) for candidate in remaining
        }
        decisions: dict[str, SelectionDecision] = {}
        used = 0
        covered_sources: set[RetrievalSource] = set()
        covered_files: set[str] = set()
        has_test = False
        while remaining:
            feasible = [
                candidate
                for candidate in remaining
                if used + costs[candidate.unit.unit_id] <= token_budget
            ]
            if not feasible:
                break
            scored = [
                (
                    self._marginal_utility(
                        candidate,
                        selected,
                        covered_sources=covered_sources,
                        covered_files=covered_files,
                        has_test=has_test,
                    ),
                    candidate,
                )
                for candidate in feasible
            ]
            scored.sort(
                key=lambda item: (
                    -(item[0] / math.sqrt(max(1, costs[item[1].unit.unit_id]))),
                    -item[0],
                    item[1].unit.path,
                    item[1].unit.start_line,
                )
            )
            utility, chosen = scored[0]
            if utility <= 0.02:
                break
            cost = costs[chosen.unit.unit_id]
            selected.append(chosen)
            remaining.remove(chosen)
            used += cost
            new_sources = set(chosen.retrieved_by) - covered_sources
            covered_sources.update(chosen.retrieved_by)
            covered_files.add(chosen.unit.path)
            has_test = has_test or chosen.unit.node_type is NodeType.TEST
            benefits: list[str] = [f"relevance {chosen.score:.3f}"]
            if new_sources:
                benefits.append(
                    "new evidence source "
                    + ", ".join(sorted(source.value for source in new_sources))
                )
            if chosen.unit.node_type is NodeType.TEST:
                benefits.append("validation coverage")
            decisions[chosen.unit.unit_id] = SelectionDecision(
                unit_id=chosen.unit.unit_id,
                file=chosen.unit.path,
                symbol=chosen.unit.qualname,
                score=chosen.score,
                estimated_tokens=cost,
                selected=True,
                reason="Selected for " + "; ".join(benefits) + ".",
                retrieved_by=tuple(chosen.retrieved_by),
                marginal_utility=utility,
            )
        for candidate in remaining:
            cost = costs[candidate.unit.unit_id]
            if used + cost > token_budget:
                reason = (
                    f"Rejected: {cost} tokens do not fit the {token_budget - used}-token remainder."
                )
            else:
                redundancy = self._redundancy(candidate, selected)
                reason = (
                    f"Rejected: marginal value reduced by {redundancy:.0%} evidence overlap."
                    if redundancy > 0.4
                    else "Rejected: lower marginal relevance or evidence diversity."
                )
            decisions[candidate.unit.unit_id] = SelectionDecision(
                unit_id=candidate.unit.unit_id,
                file=candidate.unit.path,
                symbol=candidate.unit.qualname,
                score=candidate.score,
                estimated_tokens=cost,
                selected=False,
                reason=reason,
                retrieved_by=tuple(candidate.retrieved_by),
                marginal_utility=self._marginal_utility(
                    candidate,
                    selected,
                    covered_sources=covered_sources,
                    covered_files=covered_files,
                    has_test=has_test,
                ),
            )
        ordered_decisions = tuple(
            decisions[candidate.unit.unit_id]
            for candidate in candidates
            if candidate.unit.unit_id in decisions
        )
        return OptimizationResult(tuple(selected), ordered_decisions, used)

    def _marginal_utility(
        self,
        candidate: Candidate,
        selected: list[Candidate],
        *,
        covered_sources: set[RetrievalSource],
        covered_files: set[str],
        has_test: bool,
    ) -> float:
        source_gain = len(set(candidate.retrieved_by) - covered_sources) * 0.035
        file_gain = 0.055 if candidate.unit.path not in covered_files else 0.0
        test_gain = 0.11 if candidate.unit.node_type is NodeType.TEST and not has_test else 0.0
        structural_gain = 0.03 if candidate.graph_distance == 1 else 0.0
        redundancy = self._redundancy(candidate, selected) if self.redundancy_penalty else 0.0
        return max(
            0.0,
            candidate.score
            + source_gain
            + file_gain
            + test_gain
            + structural_gain
            - redundancy * 0.3,
        )

    @staticmethod
    def _redundancy(candidate: Candidate, selected: list[Candidate]) -> float:
        candidate_terms = set(query_terms(candidate.unit.content, limit=100))
        maximum = 0.0
        for previous in selected:
            if candidate.unit.path == previous.unit.path:
                intersection = max(
                    0,
                    min(candidate.unit.end_line, previous.unit.end_line)
                    - max(candidate.unit.start_line, previous.unit.start_line)
                    + 1,
                )
                length = max(1, candidate.unit.end_line - candidate.unit.start_line + 1)
                maximum = max(maximum, intersection / length)
            previous_terms = set(query_terms(previous.unit.content, limit=100))
            union = candidate_terms | previous_terms
            if union:
                maximum = max(maximum, len(candidate_terms & previous_terms) / len(union))
        return maximum
