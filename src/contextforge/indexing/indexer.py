"""Incremental repository indexing orchestration."""

from __future__ import annotations

import time
from hashlib import sha256
from pathlib import Path

from contextforge.config import ContextForgeConfig
from contextforge.indexing.traversal import TraversalConfig, discover_source_files
from contextforge.models import IndexStats
from contextforge.parsers import PythonParser
from contextforge.parsers.base import LanguageParser
from contextforge.storage import Database


class RepositoryIndexer:
    """Incrementally parse changed repository files into persistent storage."""

    def __init__(
        self,
        repository: Path,
        database: Database,
        *,
        config: ContextForgeConfig | None = None,
        parsers: tuple[LanguageParser, ...] | None = None,
    ) -> None:
        self.repository = repository.expanduser().resolve(strict=True)
        self.database = database
        self.config = config or ContextForgeConfig.from_environment()
        self.parsers = parsers or (PythonParser(),)
        self._parsers_by_extension = {
            extension: parser for parser in self.parsers for extension in parser.extensions
        }

    def index(self) -> IndexStats:
        """Index changed files, remove stale records, and return run statistics."""
        started = time.perf_counter()
        self.database.initialize()
        traversal = TraversalConfig(
            extensions=frozenset(self._parsers_by_extension),
            max_file_bytes=self.config.max_file_bytes,
        )
        files = discover_source_files(self.repository, traversal)
        records = self.database.file_records()
        current_paths = {path.relative_to(self.repository).as_posix() for path in files}
        deleted = sorted(set(records) - current_paths)
        for relative in deleted:
            self.database.delete_file(relative)

        parsed_files = 0
        unchanged_files = 0
        units_indexed = 0
        errors: list[str] = []
        for path in files:
            relative = path.relative_to(self.repository).as_posix()
            stat = path.stat()
            digest = sha256(path.read_bytes()).hexdigest()
            previous = records.get(relative)
            if previous and previous.content_hash == digest and previous.parse_error is None:
                unchanged_files += 1
                continue
            parser = self._parsers_by_extension[path.suffix.lower()]
            try:
                parsed = parser.parse(self.repository, path)
                self.database.replace_parsed_file(
                    parsed, mtime_ns=stat.st_mtime_ns, size_bytes=stat.st_size
                )
                parsed_files += 1
                units_indexed += len(parsed.units)
            except (OSError, SyntaxError, UnicodeError, ValueError) as error:
                message = f"{relative}: {type(error).__name__}: {error}"
                errors.append(message)
                self.database.record_parse_error(
                    relative,
                    digest,
                    mtime_ns=stat.st_mtime_ns,
                    size_bytes=stat.st_size,
                    error=message,
                )
        return IndexStats(
            discovered_files=len(files),
            parsed_files=parsed_files,
            unchanged_files=unchanged_files,
            deleted_files=len(deleted),
            units_indexed=units_indexed,
            parse_errors=tuple(errors),
            elapsed_ms=(time.perf_counter() - started) * 1000,
        )
