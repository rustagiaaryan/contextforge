from __future__ import annotations

import shutil
from pathlib import Path

from contextforge import ContextForge
from contextforge.optimization.tokens import estimate_tokens
from contextforge.routing import TaskType

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"


def _engine(tmp_path: Path) -> ContextForge:
    repository = tmp_path / "repository"
    shutil.copytree(FIXTURE, repository, ignore=shutil.ignore_patterns(".contextforge"))
    return ContextForge.open(repository)


def test_engine_indexes_and_compiles_real_evidence_with_trace(tmp_path: Path) -> None:
    engine = _engine(tmp_path)

    report = engine.index()
    result = engine.compile_context(
        task="Requests through mounted applications lose their route prefix.",
        token_budget=2_000,
    )

    assert report.source.parsed_files == 4
    assert report.graph_nodes > report.source.discovered_files
    assert report.semantic_enabled
    assert result.routing.task_type is TaskType.CROSS_FILE_BUG
    assert result.items
    assert any(item.file == "app/routing.py" for item in result.items)
    assert any(item.is_test for item in result.items)
    assert result.query_evolution is not None
    assert result.decisions
    assert result.timings[-1].stage == "budget_optimization"
    assert estimate_tokens(result.to_markdown()) == result.estimated_tokens


def test_compiled_markdown_strictly_obeys_small_budget(tmp_path: Path) -> None:
    result = _engine(tmp_path).compile_context(
        task="Fix Mount.resolve route prefix and its regression test.",
        token_budget=700,
    )

    assert result.estimated_tokens <= 700
    assert estimate_tokens(result.to_markdown()) <= 700
    assert all(item.content_hash and item.source_pointer for item in result.items)
    assert "ContextForge evidence package" in result.to_markdown()
    assert result.to_json().startswith("{")
