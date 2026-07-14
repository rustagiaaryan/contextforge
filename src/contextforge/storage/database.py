"""Transactional SQLite storage for source, graph, embeddings, and Git memory."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from contextforge.models import NodeType, ParsedFile, RelationHint, SourceUnit

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    mtime_ns INTEGER NOT NULL,
    size_bytes INTEGER NOT NULL,
    indexed_at TEXT NOT NULL,
    parse_error TEXT
);
CREATE TABLE IF NOT EXISTS units (
    unit_id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL,
    path TEXT NOT NULL,
    name TEXT NOT NULL,
    qualname TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    signature TEXT NOT NULL,
    docstring TEXT NOT NULL,
    language TEXT NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    parent_id TEXT,
    is_test INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_units_path ON units(path);
CREATE INDEX IF NOT EXISTS idx_units_qualname ON units(qualname);
CREATE INDEX IF NOT EXISTS idx_units_name ON units(name);
CREATE INDEX IF NOT EXISTS idx_units_type ON units(node_type);
CREATE TABLE IF NOT EXISTS relation_hints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    edge_type TEXT NOT NULL,
    target TEXT NOT NULL,
    line INTEGER,
    confidence REAL NOT NULL,
    UNIQUE(source_id, edge_type, target)
);
CREATE INDEX IF NOT EXISTS idx_hints_source ON relation_hints(source_id);
CREATE TABLE IF NOT EXISTS graph_nodes (
    node_id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL,
    path TEXT,
    label TEXT NOT NULL,
    unit_id TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS graph_edges (
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    edge_type TEXT NOT NULL,
    confidence REAL NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(source_id, target_id, edge_type)
);
CREATE INDEX IF NOT EXISTS idx_edges_target ON graph_edges(target_id);
CREATE INDEX IF NOT EXISTS idx_edges_type ON graph_edges(edge_type);
CREATE TABLE IF NOT EXISTS embeddings (
    unit_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    vector BLOB NOT NULL,
    PRIMARY KEY(unit_id, provider)
);
CREATE TABLE IF NOT EXISTS commits (
    commit_hash TEXT PRIMARY KEY,
    message TEXT NOT NULL,
    authored_at TEXT NOT NULL,
    author_name TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS commit_files (
    commit_hash TEXT NOT NULL,
    path TEXT NOT NULL,
    status TEXT NOT NULL,
    additions INTEGER NOT NULL DEFAULT 0,
    deletions INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(commit_hash, path)
);
CREATE INDEX IF NOT EXISTS idx_commit_files_path ON commit_files(path);
CREATE TABLE IF NOT EXISTS co_changes (
    path_a TEXT NOT NULL,
    path_b TEXT NOT NULL,
    count INTEGER NOT NULL,
    PRIMARY KEY(path_a, path_b)
);
"""

FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS units_fts USING fts5(
    unit_id UNINDEXED,
    path,
    name,
    qualname,
    signature,
    docstring,
    content,
    tokenize='porter unicode61'
);
CREATE VIRTUAL TABLE IF NOT EXISTS commits_fts USING fts5(
    commit_hash UNINDEXED,
    message,
    summary,
    changed_paths,
    tokenize='porter unicode61'
);
"""


@dataclass(frozen=True)
class FileRecord:
    """Incremental-index metadata for one file."""

    path: str
    content_hash: str
    mtime_ns: int
    size_bytes: int
    parse_error: str | None


class Database:
    """Small connection-per-operation SQLite repository."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        """Create or migrate the index schema."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.executescript(SCHEMA)
            connection.executescript(FTS_SCHEMA)
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Yield a configured connection and commit or roll back atomically."""
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def file_records(self) -> dict[str, FileRecord]:
        """Return all previously indexed file metadata keyed by relative path."""
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT path, content_hash, mtime_ns, size_bytes, parse_error FROM files"
            ).fetchall()
        return {
            str(row["path"]): FileRecord(
                path=str(row["path"]),
                content_hash=str(row["content_hash"]),
                mtime_ns=int(row["mtime_ns"]),
                size_bytes=int(row["size_bytes"]),
                parse_error=str(row["parse_error"]) if row["parse_error"] else None,
            )
            for row in rows
        }

    def replace_parsed_file(self, parsed: ParsedFile, *, mtime_ns: int, size_bytes: int) -> None:
        """Atomically replace all index data owned by one parsed file."""
        with self.connection() as connection:
            old_ids = [
                str(row[0])
                for row in connection.execute(
                    "SELECT unit_id FROM units WHERE path = ?", (parsed.path,)
                )
            ]
            for unit_id in old_ids:
                connection.execute("DELETE FROM units_fts WHERE unit_id = ?", (unit_id,))
                connection.execute("DELETE FROM embeddings WHERE unit_id = ?", (unit_id,))
            connection.execute(
                "DELETE FROM relation_hints WHERE source_id IN "
                "(SELECT unit_id FROM units WHERE path = ?)",
                (parsed.path,),
            )
            connection.execute("DELETE FROM units WHERE path = ?", (parsed.path,))
            for unit in parsed.units:
                self._insert_unit(connection, unit)
            for relation in parsed.relations:
                self._insert_hint(connection, relation)
            connection.execute(
                """
                INSERT OR REPLACE INTO files(
                    path, content_hash, mtime_ns, size_bytes, indexed_at, parse_error
                ) VALUES (?, ?, ?, ?, ?, NULL)
                """,
                (
                    parsed.path,
                    parsed.content_hash,
                    mtime_ns,
                    size_bytes,
                    datetime.now(UTC).isoformat(),
                ),
            )

    def record_parse_error(
        self,
        path: str,
        content_hash: str,
        *,
        mtime_ns: int,
        size_bytes: int,
        error: str,
    ) -> None:
        """Persist a bounded parser error without aborting the whole index."""
        with self.connection() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO files(
                    path, content_hash, mtime_ns, size_bytes, indexed_at, parse_error
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    path,
                    content_hash,
                    mtime_ns,
                    size_bytes,
                    datetime.now(UTC).isoformat(),
                    error[:1000],
                ),
            )

    def delete_file(self, path: str) -> None:
        """Remove stale source units, hints, embeddings, and file metadata."""
        with self.connection() as connection:
            unit_ids = [
                str(row[0])
                for row in connection.execute("SELECT unit_id FROM units WHERE path = ?", (path,))
            ]
            for unit_id in unit_ids:
                connection.execute("DELETE FROM units_fts WHERE unit_id = ?", (unit_id,))
                connection.execute("DELETE FROM embeddings WHERE unit_id = ?", (unit_id,))
            connection.execute(
                "DELETE FROM relation_hints WHERE source_id IN "
                "(SELECT unit_id FROM units WHERE path = ?)",
                (path,),
            )
            connection.execute("DELETE FROM units WHERE path = ?", (path,))
            connection.execute("DELETE FROM files WHERE path = ?", (path,))

    def list_units(self, *, node_types: tuple[NodeType, ...] | None = None) -> list[SourceUnit]:
        """Load source units, optionally filtered by node type."""
        query = "SELECT * FROM units"
        parameters: tuple[Any, ...] = ()
        if node_types:
            placeholders = ",".join("?" for _ in node_types)
            query += f" WHERE node_type IN ({placeholders})"
            parameters = tuple(node_type.value for node_type in node_types)
        query += " ORDER BY path, start_line, unit_id"
        with self.connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._row_to_unit(row) for row in rows]

    def get_unit(self, unit_id: str) -> SourceUnit | None:
        """Load one source unit by stable identifier."""
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM units WHERE unit_id = ?", (unit_id,)).fetchone()
        return self._row_to_unit(row) if row else None

    @staticmethod
    def _insert_unit(connection: sqlite3.Connection, unit: SourceUnit) -> None:
        connection.execute(
            """
            INSERT INTO units(
                unit_id, node_type, path, name, qualname, start_line, end_line,
                signature, docstring, language, content, content_hash, parent_id, is_test
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                unit.unit_id,
                unit.node_type.value,
                unit.path,
                unit.name,
                unit.qualname,
                unit.start_line,
                unit.end_line,
                unit.signature,
                unit.docstring,
                unit.language,
                unit.content,
                unit.content_hash,
                unit.parent_id,
                int(unit.is_test),
            ),
        )
        connection.execute(
            """
            INSERT INTO units_fts(
                unit_id, path, name, qualname, signature, docstring, content
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                unit.unit_id,
                unit.path,
                unit.name,
                unit.qualname,
                unit.signature,
                unit.docstring,
                unit.content,
            ),
        )

    @staticmethod
    def _insert_hint(connection: sqlite3.Connection, relation: RelationHint) -> None:
        connection.execute(
            """
            INSERT OR REPLACE INTO relation_hints(
                source_id, edge_type, target, line, confidence
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                relation.source_id,
                relation.edge_type.value,
                relation.target,
                relation.line,
                relation.confidence,
            ),
        )

    @staticmethod
    def _row_to_unit(row: sqlite3.Row) -> SourceUnit:
        return SourceUnit(
            unit_id=str(row["unit_id"]),
            node_type=NodeType(str(row["node_type"])),
            path=str(row["path"]),
            name=str(row["name"]),
            qualname=str(row["qualname"]),
            start_line=int(row["start_line"]),
            end_line=int(row["end_line"]),
            signature=str(row["signature"]),
            docstring=str(row["docstring"]),
            language=str(row["language"]),
            content=str(row["content"]),
            content_hash=str(row["content_hash"]),
            parent_id=str(row["parent_id"]) if row["parent_id"] else None,
            is_test=bool(row["is_test"]),
        )
