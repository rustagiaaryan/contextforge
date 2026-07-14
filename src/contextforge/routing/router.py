"""Transparent deterministic task classification and retrieval routing."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class TaskType(StrEnum):
    """Coarse task types used to select evidence sources."""

    CROSS_FILE_BUG = "cross_file_bug"
    LOCAL_BUG = "local_bug"
    FEATURE = "feature"
    REFACTOR = "refactor"
    TEST_CHANGE = "test_change"
    DOCUMENTATION = "documentation"
    DEPENDENCY_CHANGE = "dependency_change"
    GENERAL = "general"


class RouteSource(StrEnum):
    """Retrieval mechanisms selectable by the router."""

    LEXICAL = "lexical"
    SEMANTIC = "semantic"
    SYMBOL = "symbol"
    CALL_GRAPH = "call_graph"
    IMPORTS = "imports"
    INHERITANCE = "inheritance"
    RELATED_TESTS = "related_tests"
    GIT_HISTORY = "git_history"
    HOTSPOTS = "hotspots"


class RetrievalRoute(BaseModel):
    """Explainable routing decision returned in every compilation trace."""

    model_config = ConfigDict(frozen=True)

    retrieval_needed: bool
    task_type: TaskType
    selected_sources: tuple[RouteSource, ...]
    reasoning_summary: str
    matched_rules: tuple[str, ...] = ()


class AdaptiveRouter:
    """Classify tasks with deterministic rules that require no external LLM."""

    def route(self, task: str) -> RetrievalRoute:
        """Return a stable source-selection decision for natural-language task text."""
        text = task.strip().lower()
        if not text or any(
            phrase in text for phrase in ("no repository context", "do not search the repository")
        ):
            return RetrievalRoute(
                retrieval_needed=False,
                task_type=TaskType.GENERAL,
                selected_sources=(),
                reasoning_summary=(
                    "The task explicitly provides no actionable repository search target."
                ),
                matched_rules=("no_retrieval",),
            )

        rules: list[str] = []
        if any(term in text for term in ("readme", "documentation", "docstring", "docs/")):
            task_type = TaskType.DOCUMENTATION
            rules.append("documentation_terms")
        elif any(
            term in text for term in ("dependency", "upgrade", "version conflict", "lockfile")
        ):
            task_type = TaskType.DEPENDENCY_CHANGE
            rules.append("dependency_terms")
        elif any(term in text for term in ("write a test", "add test", "coverage", "flaky test")):
            task_type = TaskType.TEST_CHANGE
            rules.append("test_terms")
        elif any(term in text for term in ("refactor", "rename", "extract", "move ")):
            task_type = TaskType.REFACTOR
            rules.append("refactor_terms")
        elif any(term in text for term in ("bug", "fix", "fails", "lost", "lose", "regression")):
            cross_file = any(
                term in text
                for term in (
                    "across",
                    "between",
                    "mounted",
                    "routing",
                    "integration",
                    "sub-application",
                    "call chain",
                )
            )
            task_type = TaskType.CROSS_FILE_BUG if cross_file else TaskType.LOCAL_BUG
            rules.extend(("bug_terms", "cross_file_terms" if cross_file else "local_bug_terms"))
        elif any(term in text for term in ("implement", "add support", "new feature", "introduce")):
            task_type = TaskType.FEATURE
            rules.append("feature_terms")
        else:
            task_type = TaskType.GENERAL
            rules.append("general_fallback")

        sources = [RouteSource.LEXICAL, RouteSource.SYMBOL]
        if task_type is not TaskType.DOCUMENTATION:
            sources.append(RouteSource.SEMANTIC)
        if task_type in {
            TaskType.CROSS_FILE_BUG,
            TaskType.FEATURE,
            TaskType.REFACTOR,
            TaskType.DEPENDENCY_CHANGE,
        }:
            sources.extend((RouteSource.CALL_GRAPH, RouteSource.IMPORTS))
        if task_type in {TaskType.FEATURE, TaskType.REFACTOR}:
            sources.append(RouteSource.INHERITANCE)
        if task_type in {
            TaskType.CROSS_FILE_BUG,
            TaskType.LOCAL_BUG,
            TaskType.FEATURE,
            TaskType.REFACTOR,
            TaskType.TEST_CHANGE,
        }:
            sources.append(RouteSource.RELATED_TESTS)
        if task_type in {
            TaskType.CROSS_FILE_BUG,
            TaskType.LOCAL_BUG,
            TaskType.REFACTOR,
            TaskType.DEPENDENCY_CHANGE,
        } or any(term in text for term in ("regression", "used to", "previous", "recent")):
            sources.extend((RouteSource.GIT_HISTORY, RouteSource.HOTSPOTS))
        selected = tuple(dict.fromkeys(sources))
        readable = ", ".join(source.value for source in selected)
        return RetrievalRoute(
            retrieval_needed=True,
            task_type=task_type,
            selected_sources=selected,
            reasoning_summary=(
                f"Classified as {task_type.value}; selected {readable} to cover likely "
                "implementation, structural, validation, and historical evidence."
            ),
            matched_rules=tuple(rules),
        )
