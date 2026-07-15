from __future__ import annotations

import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

import contextforge.evaluation
from contextforge.cli import app

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"
MULTILANG_FIXTURE = Path(__file__).parent / "fixtures" / "multilang_repo"
runner = CliRunner()


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    shutil.copytree(FIXTURE, repository, ignore=shutil.ignore_patterns(".contextforge"))
    return repository


def test_cli_indexes_and_reports_status(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    indexed = runner.invoke(app, ["index", str(repository), "--json"])
    status = runner.invoke(app, ["status", str(repository)])

    assert indexed.exit_code == 0, indexed.output
    assert json.loads(indexed.output)["source"]["parsed_files"] == 4
    assert status.exit_code == 0, status.output
    assert json.loads(status.output)["files"] == 4


def test_cli_compiles_task_file_as_json(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    issue = tmp_path / "issue.md"
    issue.write_text("Mounted routes lose their prefix.")

    result = runner.invoke(
        app,
        [
            "compile",
            str(repository),
            "--task-file",
            str(issue),
            "--token-budget",
            "1200",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    package = json.loads(result.output)
    assert package["estimated_tokens"] <= 1200
    assert package["items"]


def test_cli_rejects_ambiguous_task_input(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    result = runner.invoke(app, ["compile", str(repository), "--task", "x", "--task-file", "x"])
    assert result.exit_code != 0
    assert "exactly one" in result.output


def test_cli_builds_and_queries_portable_graph(tmp_path: Path) -> None:
    repository = tmp_path / "multilang"
    shutil.copytree(MULTILANG_FIXTURE, repository)

    built = runner.invoke(
        app,
        [
            "graph",
            "build",
            str(repository),
            "--cluster",
            "networkx",
            "--json",
        ],
    )

    assert built.exit_code == 0, built.output
    report = json.loads(built.output)
    assert report["files"] == 4
    graph_file = repository / "contextforge-out" / "graph.json"
    queried = runner.invoke(
        app,
        ["graph", "query", str(graph_file), "--question", "route mount", "--limit", "8"],
    )
    assert queried.exit_code == 0, queried.output
    assert json.loads(queried.output)["nodes"]


def test_cli_installs_project_scoped_graph_skill(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    installed = runner.invoke(app, ["skill", "install", str(repository)])

    assert installed.exit_code == 0, installed.output
    skill = repository / ".agents" / "skills" / "contextforge-graph" / "SKILL.md"
    metadata = skill.parent / "agents" / "openai.yaml"
    assert skill.is_file()
    assert metadata.is_file()
    assert "name: contextforge-graph" in skill.read_text(encoding="utf-8")

    duplicate = runner.invoke(app, ["skill", "install", str(repository)])
    assert duplicate.exit_code != 0
    refreshed = runner.invoke(app, ["skill", "install", str(repository), "--overwrite"])
    assert refreshed.exit_code == 0, refreshed.output


def test_cli_writes_historical_benchmark_output(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text("{}\n", encoding="utf-8")
    output = tmp_path / "result.json"

    class FakeRun:
        def model_dump_json(self, *, indent: int) -> str:
            assert indent == 2
            return json.dumps({"task_count": 1}, indent=indent)

    class FakeBenchmark:
        def __init__(self, selected_manifest: Path) -> None:
            assert selected_manifest == manifest

        def run(self, workspace: Path, **options: object) -> FakeRun:
            assert workspace == Path(".contextforge/test-history")
            assert options["token_budget"] == 8000
            return FakeRun()

    monkeypatch.setattr(contextforge.evaluation, "HistoricalPatchBenchmark", FakeBenchmark)
    result = runner.invoke(
        app,
        [
            "evaluate-history",
            "--manifest",
            str(manifest),
            "--workspace",
            ".contextforge/test-history",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(output.read_text(encoding="utf-8"))["task_count"] == 1
