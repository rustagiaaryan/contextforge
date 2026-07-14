from pathlib import Path

from contextforge.indexing import discover_source_files

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"


def test_discovery_respects_gitignore_and_is_deterministic() -> None:
    relative = [path.relative_to(FIXTURE).as_posix() for path in discover_source_files(FIXTURE)]
    assert relative == [
        "app/__init__.py",
        "app/routing.py",
        "app/utils.py",
        "tests/test_routing.py",
    ]
    assert "ignored.py" not in relative
