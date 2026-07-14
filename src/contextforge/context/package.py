"""Serializable, explainable context evidence packages."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from contextforge.optimization.selector import SelectionDecision
from contextforge.retrieval.evolution import QueryEvolutionTrace
from contextforge.retrieval.history import CommitEvidence
from contextforge.retrieval.models import Candidate, RetrievalSource
from contextforge.routing import RetrievalRoute


class StageTiming(BaseModel):
    """One measured pipeline stage."""

    model_config = ConfigDict(frozen=True)

    stage: str
    elapsed_ms: float = Field(ge=0.0)
    item_count: int = Field(default=0, ge=0)


class EvidenceItem(BaseModel):
    """A selected, source-backed evidence range."""

    model_config = ConfigDict(frozen=True)

    file: str
    symbol: str
    start_line: int
    end_line: int
    estimated_tokens: int
    score: float
    why_selected: str
    retrieved_by: tuple[RetrievalSource, ...]
    content_hash: str
    content: str
    source_pointer: str
    signature: str = ""
    is_test: bool = False

    @classmethod
    def from_candidate(cls, candidate: Candidate, decision: SelectionDecision) -> EvidenceItem:
        """Convert an optimized candidate into the stable public schema."""
        return cls(
            file=candidate.unit.path,
            symbol=candidate.unit.qualname,
            start_line=candidate.unit.start_line,
            end_line=candidate.unit.end_line,
            estimated_tokens=decision.estimated_tokens,
            score=candidate.score,
            why_selected=decision.reason + " " + " ".join(candidate.reasons[:3]),
            retrieved_by=tuple(candidate.retrieved_by),
            content_hash=candidate.unit.content_hash,
            content=candidate.unit.content,
            source_pointer=f"contextforge://unit/{candidate.unit.unit_id}",
            signature=candidate.unit.signature,
            is_test=candidate.unit.is_test,
        )


class EvidencePackage(BaseModel):
    """Complete task context, provenance, decisions, history, and timing trace."""

    task: str
    repository: str
    token_budget: int
    estimated_tokens: int
    routing: RetrievalRoute
    items: tuple[EvidenceItem, ...]
    relevant_commits: tuple[CommitEvidence, ...] = ()
    query_evolution: QueryEvolutionTrace | None = None
    timings: tuple[StageTiming, ...] = ()
    decisions: tuple[SelectionDecision, ...] = ()
    initial_anchor_ids: tuple[str, ...] = ()
    graph_expansion_count: int = 0
    hotspot_files: tuple[tuple[str, int], ...] = ()
    semantic_enabled: bool = True

    def to_markdown(self) -> str:
        """Render an agent-ready Markdown context package."""
        sources = ", ".join(source.value for source in self.routing.selected_sources) or "none"
        lines = [
            "# ContextForge evidence package",
            "",
            f"**Task:** {self.task}",
            f"**Repository:** `{self.repository}`",
            f"**Budget:** {self.estimated_tokens}/{self.token_budget} estimated tokens",
            f"**Route:** `{self.routing.task_type.value}` via {sources}",
            f"**Routing rationale:** {self.routing.reasoning_summary}",
            "",
            "## Selected source evidence",
            "",
        ]
        if not self.items:
            lines.extend(["No source evidence was selected.", ""])
        for item in self.items:
            provenance = ", ".join(source.value for source in item.retrieved_by)
            lines.extend(
                [
                    f"### `{item.symbol}`",
                    "",
                    f"`{item.file}:{item.start_line}-{item.end_line}` · score "
                    f"{item.score:.3f} · {item.estimated_tokens} tokens · {provenance}",
                    "",
                    item.why_selected,
                    "",
                    f"Pointer: `{item.source_pointer}` · hash `{item.content_hash[:12]}`",
                    "",
                    f"```{self._language(item.file)}",
                    item.content.rstrip(),
                    "```",
                    "",
                ]
            )
        if self.relevant_commits:
            lines.extend(["## Relevant Git memory", ""])
            for commit in self.relevant_commits:
                lines.append(
                    f"- `{commit.commit_hash[:10]}` {commit.message} (score {commit.score:.3f}) — "
                    + "; ".join(commit.reasons)
                )
            lines.append("")
        if self.query_evolution and self.query_evolution.derived_concepts:
            lines.extend(
                [
                    "## Retrieval trace",
                    "",
                    "Evolved once with: "
                    + ", ".join(self.query_evolution.derived_concepts)
                    + f"; added {self.query_evolution.added_candidate_count} candidates.",
                    "",
                ]
            )
        if self.timings:
            timing = ", ".join(f"{item.stage} {item.elapsed_ms:.1f}ms" for item in self.timings)
            lines.extend([f"Timings: {timing}.", ""])
        return "\n".join(lines).rstrip() + "\n"

    def to_json(self, *, indent: int = 2) -> str:
        """Render the complete machine-readable package."""
        return self.model_dump_json(indent=indent)

    @staticmethod
    def _language(path: str) -> str:
        return "python" if path.endswith((".py", ".pyi")) else "text"
