from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from contextforge.graph import GraphBuilder
from contextforge.impact import ImpactAnalyzer
from contextforge.impact.git_changes import GitChangeReader
from contextforge.indexing import RepositoryIndexer
from contextforge.storage import Database

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"


def _git(repository: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )


def _repository(tmp_path: Path) -> tuple[Path, ImpactAnalyzer]:
    repository = tmp_path / "repository"
    shutil.copytree(FIXTURE, repository)
    shutil.rmtree(repository / ".contextforge", ignore_errors=True)
    _git(repository, "init", "-b", "main")
    _git(repository, "config", "user.email", "contextforge@example.invalid")
    _git(repository, "config", "user.name", "ContextForge Tests")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "fixture")
    database = Database(tmp_path / "index.sqlite3")
    RepositoryIndexer(repository, database).index()
    GraphBuilder(repository, database).build()
    return repository, ImpactAnalyzer(repository, database)


def test_parse_diff_tracks_ranges_and_renames() -> None:
    diff = """\
diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -4,2 +4,3 @@
diff --git a/new.py b/new.py
new file mode 100644
--- /dev/null
+++ b/new.py
@@ -0,0 +1,2 @@
diff --git a/gone.py b/gone.py
deleted file mode 100644
--- a/gone.py
+++ /dev/null
@@ -1,3 +0,0 @@
diff --git a/old.py b/moved.py
similarity index 80%
rename from old.py
rename to moved.py
--- a/old.py
+++ b/moved.py
@@ -8 +8 @@
"""

    changes = GitChangeReader.parse_diff(diff)

    assert [change.model_dump() for change in changes] == [
        {
            "path": "app.py",
            "start_line": 4,
            "end_line": 6,
            "status": "modified",
            "old_path": None,
        },
        {
            "path": "gone.py",
            "start_line": 0,
            "end_line": 0,
            "status": "deleted",
            "old_path": None,
        },
        {
            "path": "moved.py",
            "start_line": 8,
            "end_line": 8,
            "status": "renamed",
            "old_path": "old.py",
        },
        {
            "path": "new.py",
            "start_line": 1,
            "end_line": 2,
            "status": "added",
            "old_path": None,
        },
    ]


def test_analyze_changes_maps_narrowest_symbol_and_keeps_unresolved_paths(
    tmp_path: Path,
) -> None:
    repository, analyzer = _repository(tmp_path)
    utility = repository / "app" / "utils.py"
    utility.write_text(
        utility.read_text(encoding="utf-8").replace(
            "return f\"{prefix.rstrip('/')}/{path.lstrip('/')}\"",
            "return f\"/{prefix.strip('/')}/{path.strip('/')}\"",
        ),
        encoding="utf-8",
    )
    (repository / "scratch.py").write_text("value = 1\n", encoding="utf-8")
    (repository / "app" / "__init__.py").unlink()

    report = analyzer.analyze_changes()

    assert [seed.qualname for seed in report.seeds] == ["app.utils.join_path"]
    assert {symbol.qualname for symbol in report.impacted} >= {
        "app.routing.Mount.resolve",
        "app.routing.dispatch",
    }
    assert report.changed_files == ("app/__init__.py", "app/utils.py", "scratch.py")
    assert report.unresolved == ("app/__init__.py", "scratch.py")


def test_git_change_reader_reports_invalid_repository_and_revision(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(ValueError, match="not a Git repository"):
        GitChangeReader(plain).read()

    repository, _ = _repository(tmp_path / "git")
    with pytest.raises(ValueError, match="invalid Git revision: missing-ref"):
        GitChangeReader(repository).read(base="missing-ref")


def test_git_change_reader_combines_branch_commit_and_staged_change(tmp_path: Path) -> None:
    repository, _ = _repository(tmp_path)
    _git(repository, "checkout", "-b", "feature")
    routing = repository / "app" / "routing.py"
    routing.write_text(
        routing.read_text(encoding="utf-8").replace(
            '"""Build the delegated path."""',
            '"""Build a delegated child path."""',
        ),
        encoding="utf-8",
    )
    _git(repository, "add", "app/routing.py")
    _git(repository, "commit", "-m", "change routing")
    test_file = repository / "tests" / "test_routing.py"
    test_file.write_text(
        test_file.read_text(encoding="utf-8").replace("/api/users", "/api/accounts"),
        encoding="utf-8",
    )
    _git(repository, "add", "tests/test_routing.py")

    changes = GitChangeReader(repository).read(base="main")

    assert {change.path for change in changes} == {
        "app/routing.py",
        "tests/test_routing.py",
    }
    assert all(change.status == "modified" for change in changes)
