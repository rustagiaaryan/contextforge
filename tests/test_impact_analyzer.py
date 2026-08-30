from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from contextforge.graph import GraphBuilder
from contextforge.impact import ImpactAnalyzer, RiskLevel
from contextforge.indexing import RepositoryIndexer
from contextforge.models import EdgeType
from contextforge.storage import Database

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"


def _analyzer(tmp_path: Path) -> ImpactAnalyzer:
    repository = tmp_path / "repository"
    shutil.copytree(FIXTURE, repository)
    database = Database(tmp_path / "index.sqlite3")
    RepositoryIndexer(repository, database).index()
    GraphBuilder(repository, database).build()
    return ImpactAnalyzer(repository, database)


def _source_analyzer(tmp_path: Path, source: str) -> ImpactAnalyzer:
    repository = tmp_path / "source-repository"
    repository.mkdir(parents=True)
    (repository / "service.py").write_text(source, encoding="utf-8")
    database = Database(tmp_path / "source-index.sqlite3")
    RepositoryIndexer(repository, database).index()
    GraphBuilder(repository, database).build()
    return ImpactAnalyzer(repository, database)


def test_symbol_impact_finds_callers_and_tests(tmp_path: Path) -> None:
    report = _analyzer(tmp_path).analyze_symbol("app.utils.join_path")

    impacted = {symbol.qualname: symbol for symbol in report.impacted}
    assert impacted["app.routing.Mount.resolve"].distance == 1
    assert impacted["app.routing.dispatch"].distance == 2
    assert [step.edge_type for step in impacted["app.routing.dispatch"].relationship_path] == [
        EdgeType.CALLS,
        EdgeType.CALLS,
    ]
    assert (
        impacted["app.routing.dispatch"].path_confidence
        <= impacted["app.routing.Mount.resolve"].path_confidence
    )
    assert not any(symbol.is_test for symbol in report.impacted)
    assert {symbol.qualname for symbol in report.related_tests} == {
        "tests.test_routing.test_mounted_prefix_is_preserved"
    }
    assert report.risk_level is RiskLevel.LOW
    assert report.truncated is False


def test_symbol_resolution_is_exact_and_reports_ambiguity(tmp_path: Path) -> None:
    analyzer = _analyzer(tmp_path)

    with pytest.raises(ValueError, match=r"Unknown symbol: join_pat"):
        analyzer.analyze_symbol("join_pat")

    with analyzer.database.connection() as connection:
        original = connection.execute("SELECT * FROM units WHERE name = 'dispatch'").fetchone()
        assert original is not None
        values = tuple(original)
        duplicate = list(values)
        duplicate[0] = "function:app/alternate.py:dispatch"
        duplicate[2] = "app/alternate.py"
        duplicate[4] = "app.alternate.dispatch"
        placeholders = ",".join("?" for _ in duplicate)
        connection.execute(f"INSERT INTO units VALUES ({placeholders})", duplicate)

    with pytest.raises(ValueError, match=r"Ambiguous symbol 'dispatch'.*app.alternate.dispatch"):
        analyzer.analyze_symbol("dispatch")


def test_risk_increases_for_broad_public_api_impact(tmp_path: Path) -> None:
    medium_analyzer = _source_analyzer(
        tmp_path / "medium",
        """\
def public_api() -> int:
    return 1

def caller_one() -> int:
    return public_api()

def caller_two() -> int:
    return public_api()

def caller_three() -> int:
    return public_api()

def caller_four() -> int:
    return public_api()
""",
    )
    analyzer = _source_analyzer(
        tmp_path,
        """\
def public_api() -> int:
    return 1

def caller_one() -> int:
    return public_api()

def caller_two() -> int:
    return public_api()

def caller_three() -> int:
    return public_api()

def caller_four() -> int:
    return public_api()

def caller_five() -> int:
    return public_api()
""",
    )

    medium = medium_analyzer.analyze_symbol("public_api")
    truncated = analyzer.analyze_symbol("public_api", limit=4)
    full = analyzer.analyze_symbol("public_api")

    assert medium.risk_level is RiskLevel.MEDIUM
    assert "4 impacted production symbols" in medium.risk_reasons
    assert truncated.risk_level is RiskLevel.HIGH
    assert "result limit reached; additional dependents exist" in truncated.risk_reasons
    assert full.risk_level is RiskLevel.HIGH
    assert "public seed has 5 direct dependents" in full.risk_reasons


def test_traversal_keeps_strongest_equal_length_path(tmp_path: Path) -> None:
    analyzer = _source_analyzer(
        tmp_path,
        """\
def target() -> int:
    return 1

def weak() -> int:
    return target()

def strong() -> int:
    return target()

def dependent() -> int:
    return weak() + strong()
""",
    )
    units = {unit.name: unit for unit in analyzer.database.list_units()}
    with analyzer.database.connection() as connection:
        connection.execute(
            "UPDATE graph_edges SET confidence = 0.4 WHERE source_id = ? AND target_id = ?",
            (units["weak"].unit_id, units["target"].unit_id),
        )
        connection.execute(
            "UPDATE graph_edges SET confidence = 0.72 WHERE source_id = ? AND target_id = ?",
            (units["strong"].unit_id, units["target"].unit_id),
        )
        connection.execute(
            "UPDATE graph_edges SET confidence = 1.0 WHERE source_id = ? AND target_id IN (?, ?)",
            (
                units["dependent"].unit_id,
                units["weak"].unit_id,
                units["strong"].unit_id,
            ),
        )

    first = analyzer.analyze_symbol("target")
    second = analyzer.analyze_symbol("target")
    dependent = next(symbol for symbol in first.impacted if symbol.qualname == "service.dependent")

    assert dependent.path_confidence == pytest.approx(0.72)
    assert dependent.relationship_path[-1].source_id == units["strong"].unit_id
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
