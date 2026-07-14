from __future__ import annotations

import shutil
from pathlib import Path

from contextforge.indexing import RepositoryIndexer
from contextforge.models import NodeType
from contextforge.storage import Database

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"


def _copy_fixture(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    shutil.copytree(FIXTURE, repository)
    return repository


def test_indexer_persists_units_and_skips_unchanged_files(tmp_path: Path) -> None:
    repository = _copy_fixture(tmp_path)
    database = Database(tmp_path / "index.sqlite3")
    indexer = RepositoryIndexer(repository, database)

    first = indexer.index()
    second = indexer.index()

    assert first.discovered_files == 4
    assert first.parsed_files == 4
    assert first.units_indexed > 4
    assert second.parsed_files == 0
    assert second.unchanged_files == 4
    units = database.list_units(node_types=(NodeType.METHOD,))
    assert [unit.qualname for unit in units] == [
        "app.routing.Mount.__init__",
        "app.routing.Mount.resolve",
    ]


def test_indexer_replaces_changed_and_removes_deleted_files(tmp_path: Path) -> None:
    repository = _copy_fixture(tmp_path)
    database = Database(tmp_path / "index.sqlite3")
    indexer = RepositoryIndexer(repository, database)
    indexer.index()

    utils = repository / "app" / "utils.py"
    utils.write_text(utils.read_text() + "\n\ndef normalize(path: str) -> str:\n    return path\n")
    (repository / "app" / "__init__.py").unlink()
    stats = indexer.index()

    assert stats.parsed_files == 1
    assert stats.deleted_files == 1
    qualnames = {unit.qualname for unit in database.list_units()}
    assert "app.utils.normalize" in qualnames
    assert "app" not in qualnames


def test_indexer_records_syntax_errors_without_aborting(tmp_path: Path) -> None:
    repository = _copy_fixture(tmp_path)
    broken = repository / "app" / "broken.py"
    broken.write_text("def invalid(:\n")
    database = Database(tmp_path / "index.sqlite3")

    stats = RepositoryIndexer(repository, database).index()

    assert stats.discovered_files == 5
    assert stats.parsed_files == 4
    assert len(stats.parse_errors) == 1
    assert "broken.py: SyntaxError" in stats.parse_errors[0]
