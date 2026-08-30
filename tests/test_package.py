from pathlib import Path

from typer.testing import CliRunner

from contextforge import __version__
from contextforge.cli import app
from contextforge.impact import ImpactAnalyzer
from contextforge.skill_install import install_graph_skill


def test_package_has_version() -> None:
    assert __version__ == "0.1.0"


def test_impact_api_commands_and_bundled_workflow_ship_together(tmp_path: Path) -> None:
    assert ImpactAnalyzer.__module__ == "contextforge.impact.analyzer"
    runner = CliRunner()
    assert runner.invoke(app, ["impact", "--help"]).exit_code == 0
    assert runner.invoke(app, ["changes", "--help"]).exit_code == 0

    repository = tmp_path / "repository"
    repository.mkdir()
    skill = install_graph_skill(repository) / "SKILL.md"
    instructions = skill.read_text(encoding="utf-8")

    assert "contextforge impact" in instructions
    assert "contextforge changes" in instructions
