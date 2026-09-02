from __future__ import annotations

import json
import shutil
import subprocess
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


def test_cli_reports_symbol_impact_as_json_and_human_summary(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    machine = runner.invoke(
        app,
        ["impact", str(repository), "--symbol", "app.utils.join_path", "--json"],
    )
    human = runner.invoke(
        app,
        ["impact", str(repository), "--symbol", "app.utils.join_path"],
    )

    assert machine.exit_code == 0, machine.output
    report = json.loads(machine.output)
    assert report["mode"] == "symbol"
    assert report["risk_level"] == "low"
    assert report["impacted_files"] == ["app/routing.py"]
    assert human.exit_code == 0, human.output
    assert "LOW" in human.output
    assert "app.routing.Mount.resolve" in human.output
    assert "test_mounted_prefix_is_preserved" in human.output


def test_cli_impact_rejects_unknown_symbol_concisely(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    result = runner.invoke(app, ["impact", str(repository), "--symbol", "missing"])

    assert result.exit_code != 0
    assert "Unknown symbol: missing" in result.output
    assert "Traceback" not in result.output


def test_cli_reports_working_tree_change_impact_as_json(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    for arguments in (
        ("init", "-b", "main"),
        ("config", "user.email", "contextforge@example.invalid"),
        ("config", "user.name", "ContextForge Tests"),
        ("add", "."),
        ("commit", "-m", "fixture"),
    ):
        subprocess.run(
            ["git", *arguments],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        )
    utility = repository / "app" / "utils.py"
    utility.write_text(
        utility.read_text(encoding="utf-8").replace("Join two", "Join URL"),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["changes", str(repository), "--json"])

    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["mode"] == "changes"
    assert report["changed_files"] == ["app/utils.py"]
    assert report["seeds"][0]["qualname"] == "app.utils.join_path"


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

    hubs = runner.invoke(
        app,
        ["graph", "hubs", str(graph_file), "--limit", "3"],
    )
    assert hubs.exit_code == 0, hubs.output
    ranked = json.loads(hubs.output)
    assert len(ranked) == 3
    assert ranked[0]["centrality"] == 1.0
    assert [node["centrality"] for node in ranked] == sorted(
        (node["centrality"] for node in ranked),
        reverse=True,
    )
    assert {"id", "label", "kind", "centrality", "degree", "source_file", "community"} <= set(
        ranked[0]
    )


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
