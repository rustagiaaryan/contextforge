from __future__ import annotations

import subprocess
from pathlib import Path

from contextforge.embeddings import LocalHashEmbeddingProvider
from contextforge.graph import GraphBuilder
from contextforge.indexing import RepositoryIndexer
from contextforge.retrieval import GitHistoryIndexer, GitHistoryRetriever
from contextforge.storage import Database


def _git(repository: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "history_repo"
    repository.mkdir()
    _git(repository, "init", "-b", "main")
    _git(repository, "config", "user.name", "ContextForge Test")
    _git(repository, "config", "user.email", "test@example.invalid")
    (repository / "router.py").write_text("def mount(prefix, path):\n    return path\n")
    (repository / "test_router.py").write_text(
        "from router import mount\n\ndef test_prefix():\n    assert mount('/api', '/x') == '/x'\n"
    )
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "feat: add mounted routing")
    (repository / "router.py").write_text(
        "def mount(prefix, path):\n    return prefix.rstrip('/') + '/' + path.lstrip('/')\n"
    )
    (repository / "test_router.py").write_text(
        "from router import mount\n\ndef test_prefix():\n"
        "    assert mount('/api', '/x') == '/api/x'\n"
    )
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "fix: preserve mounted route prefix")
    (repository / "notes.py").write_text("RELEASE = 'ok'\n")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "chore: add release metadata")
    return repository


def test_git_memory_indexes_searches_and_gates_history(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    database = Database(tmp_path / "index.sqlite3")
    RepositoryIndexer(repository, database).index()
    GraphBuilder(repository, database).build()
    provider = LocalHashEmbeddingProvider(64)

    stats = GitHistoryIndexer(repository, database, provider=provider).index()
    results = GitHistoryRetriever(database, provider=provider).search(
        "mounted applications lose their route prefix",
        anchor_paths={"router.py"},
    )

    assert stats.available and stats.commits_indexed == 3
    assert results
    assert results[0].message == "fix: preserve mounted route prefix"
    assert "router.py" in results[0].anchor_overlap
    assert all(result.score >= 0.25 for result in results)


def test_git_memory_exposes_cochanges_and_hotspots(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    database = Database(tmp_path / "index.sqlite3")
    RepositoryIndexer(repository, database).index()
    GraphBuilder(repository, database).build()
    GitHistoryIndexer(repository, database).index()
    history = GitHistoryRetriever(database)

    assert history.co_changed_files("router.py")[0] == ("test_router.py", 2)
    assert history.hotspots()[0] in {("router.py", 2), ("test_router.py", 2)}


def test_git_memory_tracks_file_renames(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _git(repository, "mv", "notes.py", "release_notes.py")
    _git(repository, "commit", "-m", "refactor: rename release metadata")
    database = Database(tmp_path / "index.sqlite3")
    RepositoryIndexer(repository, database).index()
    GraphBuilder(repository, database).build()

    GitHistoryIndexer(repository, database).index()
    renames = GitHistoryRetriever(database).recent_renames()

    assert renames[0]["old_path"] == "notes.py"
    assert renames[0]["new_path"] == "release_notes.py"


def test_git_memory_scopes_paths_to_selected_subdirectory(tmp_path: Path) -> None:
    root = tmp_path / "monorepo"
    package = root / "packages" / "router"
    package.mkdir(parents=True)
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.name", "ContextForge Test")
    _git(root, "config", "user.email", "test@example.invalid")
    (package / "routing.py").write_text("def dispatch():\n    return True\n")
    (root / "unrelated.py").write_text("VALUE = 1\n")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "feat: add router package and unrelated code")
    database = Database(tmp_path / "subdir.sqlite3")
    RepositoryIndexer(package, database).index()
    GraphBuilder(package, database).build()

    GitHistoryIndexer(package, database).index()
    with database.connection() as connection:
        paths = {str(row["path"]) for row in connection.execute("SELECT path FROM commit_files")}

    assert paths == {"routing.py"}
