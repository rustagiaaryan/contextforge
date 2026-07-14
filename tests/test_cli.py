from __future__ import annotations

import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from contextforge.cli import app

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"
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
