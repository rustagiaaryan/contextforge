"""Confidence-gated Git history as episodic repository memory."""

from __future__ import annotations

import json
import math
import struct
import subprocess
from collections import Counter
from datetime import UTC, datetime
from hashlib import sha256
from itertools import combinations
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from contextforge.embeddings import EmbeddingProvider
from contextforge.models import EdgeType, NodeType
from contextforge.retrieval.text import fts_query
from contextforge.storage import Database


class GitIndexStats(BaseModel):
    """Git memory indexing result."""

    model_config = ConfigDict(frozen=True)

    available: bool
    commits_indexed: int = 0
    changed_file_records: int = 0
    co_change_pairs: int = 0
    error: str | None = None


class CommitEvidence(BaseModel):
    """A gated historical change relevant to the current task."""

    model_config = ConfigDict(frozen=True)

    commit_hash: str
    message: str
    authored_at: datetime
    author_name: str
    changed_files: tuple[str, ...]
    summary: str
    score: float = Field(ge=0.0, le=1.0)
    reasons: tuple[str, ...]
    lexical_score: float = 0.0
    semantic_score: float = 0.0
    anchor_overlap: tuple[str, ...] = ()


def _run_git(repository: Path, arguments: list[str]) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    return completed.stdout


def _pack(vector: list[float]) -> bytes:
    return struct.pack(f"<{len(vector)}f", *vector)


def _unpack(data: bytes, dimensions: int) -> tuple[float, ...]:
    return struct.unpack(f"<{dimensions}f", data)


class GitHistoryIndexer:
    """Index commit metadata, compact diff summaries, hotspots, and co-changes."""

    def __init__(
        self,
        repository: Path,
        database: Database,
        *,
        provider: EmbeddingProvider | None = None,
        max_commits: int = 500,
    ) -> None:
        self.repository = repository.resolve(strict=True)
        self.database = database
        self.provider = provider
        self.max_commits = max(1, max_commits)

    def index(self) -> GitIndexStats:
        """Rebuild bounded Git memory without failing non-Git repositories."""
        try:
            if _run_git(self.repository, ["rev-parse", "--is-inside-work-tree"]).strip() != "true":
                return GitIndexStats(available=False, error="Not a Git work tree")
            output = _run_git(
                self.repository,
                [
                    "log",
                    "--no-merges",
                    f"--max-count={self.max_commits}",
                    "--format=%x1e%H%x1f%aI%x1f%an%x1f%s",
                    "--numstat",
                ],
            )
        except (OSError, subprocess.SubprocessError) as error:
            return GitIndexStats(available=False, error=f"{type(error).__name__}: {error}")
        records = self._parse_log(output)
        co_changes: Counter[tuple[str, str]] = Counter()
        for _, _, _, _, files in records:
            paths = sorted({path for path, _, _ in files})
            co_changes.update(combinations(paths, 2))
        with self.database.connection() as connection:
            connection.execute("DELETE FROM commits_fts")
            connection.execute("DELETE FROM commit_files")
            connection.execute("DELETE FROM commits")
            connection.execute("DELETE FROM co_changes")
            connection.execute(
                "DELETE FROM graph_edges WHERE edge_type IN (?, ?)",
                (
                    EdgeType.CHANGED_IN.value,
                    EdgeType.CO_CHANGED_WITH.value,
                ),
            )
            connection.execute(
                "DELETE FROM graph_nodes WHERE node_type = ?", (NodeType.COMMIT.value,)
            )
            indexed_paths = {
                str(row["path"]): str(row["unit_id"])
                for row in connection.execute(
                    "SELECT path, unit_id FROM units WHERE node_type = ?", (NodeType.FILE.value,)
                )
            }
            for commit_hash, authored_at, author, message, files in records:
                summary = "; ".join(
                    f"{path} (+{additions}/-{deletions})"
                    for path, additions, deletions in files[:30]
                )
                connection.execute(
                    """
                    INSERT INTO commits(commit_hash, message, authored_at, author_name, summary)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (commit_hash, message, authored_at, author, summary),
                )
                paths = [path for path, _, _ in files]
                connection.execute(
                    "INSERT INTO commits_fts(commit_hash, message, summary, changed_paths) "
                    "VALUES (?, ?, ?, ?)",
                    (commit_hash, message, summary, " ".join(paths)),
                )
                commit_id = f"commit:{commit_hash}"
                connection.execute(
                    """
                    INSERT OR REPLACE INTO graph_nodes(
                        node_id, node_type, path, label, unit_id, metadata_json
                    ) VALUES (?, ?, NULL, ?, NULL, ?)
                    """,
                    (
                        commit_id,
                        NodeType.COMMIT.value,
                        message,
                        json.dumps({"authored_at": authored_at, "commit_hash": commit_hash}),
                    ),
                )
                for path, additions, deletions in files:
                    connection.execute(
                        """
                        INSERT INTO commit_files(
                            commit_hash, path, status, additions, deletions
                        ) VALUES (?, ?, 'M', ?, ?)
                        """,
                        (commit_hash, path, additions, deletions),
                    )
                    if file_id := indexed_paths.get(path):
                        connection.execute(
                            """
                            INSERT OR REPLACE INTO graph_edges(
                                source_id, target_id, edge_type, confidence, metadata_json
                            ) VALUES (?, ?, ?, 1.0, ?)
                            """,
                            (
                                file_id,
                                commit_id,
                                EdgeType.CHANGED_IN.value,
                                json.dumps({"additions": additions, "deletions": deletions}),
                            ),
                        )
            for (path_a, path_b), count in co_changes.items():
                connection.execute(
                    "INSERT INTO co_changes(path_a, path_b, count) VALUES (?, ?, ?)",
                    (path_a, path_b, count),
                )
                if path_a in indexed_paths and path_b in indexed_paths:
                    maximum = max(co_changes.values(), default=1)
                    confidence = min(1.0, count / maximum)
                    for source, target in ((path_a, path_b), (path_b, path_a)):
                        connection.execute(
                            """
                            INSERT OR REPLACE INTO graph_edges(
                                source_id, target_id, edge_type, confidence, metadata_json
                            ) VALUES (?, ?, ?, ?, ?)
                            """,
                            (
                                indexed_paths[source],
                                indexed_paths[target],
                                EdgeType.CO_CHANGED_WITH.value,
                                confidence,
                                json.dumps({"count": count}),
                            ),
                        )
        if self.provider:
            self._index_embeddings(records)
        return GitIndexStats(
            available=True,
            commits_indexed=len(records),
            changed_file_records=sum(len(record[4]) for record in records),
            co_change_pairs=len(co_changes),
        )

    def _index_embeddings(
        self, records: list[tuple[str, str, str, str, list[tuple[str, int, int]]]]
    ) -> None:
        if not self.provider:
            return
        with self.database.connection() as connection:
            cached = {
                str(row["unit_id"]): str(row["content_hash"])
                for row in connection.execute(
                    "SELECT unit_id, content_hash FROM embeddings WHERE provider = ? "
                    "AND unit_id LIKE 'commit:%'",
                    (self.provider.name,),
                )
            }
        pending: list[tuple[str, str, str]] = []
        for commit_hash, _, _, message, files in records:
            text = f"{message}\n" + "\n".join(path for path, _, _ in files)
            content_hash = sha256(text.encode()).hexdigest()
            unit_id = f"commit:{commit_hash}"
            if cached.get(unit_id) != content_hash:
                pending.append((unit_id, content_hash, text))
        for offset in range(0, len(pending), 64):
            batch = pending[offset : offset + 64]
            try:
                vectors = self.provider.embed([item[2] for item in batch])
            except Exception:
                return
            if len(vectors) != len(batch):
                return
            with self.database.connection() as connection:
                for (unit_id, content_hash, _), vector in zip(batch, vectors, strict=True):
                    if len(vector) != self.provider.dimensions:
                        return
                    connection.execute(
                        """
                        INSERT OR REPLACE INTO embeddings(
                            unit_id, provider, content_hash, dimensions, vector
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            unit_id,
                            self.provider.name,
                            content_hash,
                            self.provider.dimensions,
                            _pack(vector),
                        ),
                    )

    @staticmethod
    def _parse_log(
        output: str,
    ) -> list[tuple[str, str, str, str, list[tuple[str, int, int]]]]:
        records: list[tuple[str, str, str, str, list[tuple[str, int, int]]]] = []
        for block in output.split("\x1e"):
            block = block.strip()
            if not block:
                continue
            lines = block.splitlines()
            header = lines[0].split("\x1f", maxsplit=3)
            if len(header) != 4:
                continue
            files: list[tuple[str, int, int]] = []
            for line in lines[1:]:
                parts = line.split("\t", maxsplit=2)
                if len(parts) != 3:
                    continue
                additions = int(parts[0]) if parts[0].isdigit() else 0
                deletions = int(parts[1]) if parts[1].isdigit() else 0
                files.append((parts[2], additions, deletions))
            records.append((header[0], header[1], header[2], header[3], files))
        return records


class GitHistoryRetriever:
    """Retrieve historical patches only when confidence gates are met."""

    def __init__(
        self,
        database: Database,
        *,
        provider: EmbeddingProvider | None = None,
    ) -> None:
        self.database = database
        self.provider = provider

    def search(
        self,
        task: str,
        *,
        anchor_paths: set[str] | None = None,
        limit: int = 8,
        minimum_score: float = 0.25,
    ) -> list[CommitEvidence]:
        """Rank task-related commits using overlap, semantics, anchors, recency, and validity."""
        if limit < 1:
            return []
        lexical = self._lexical_scores(task, limit=max(30, limit * 5))
        semantic = self._semantic_scores(task)
        anchor_paths = anchor_paths or set()
        with self.database.connection() as connection:
            commits = connection.execute("SELECT * FROM commits").fetchall()
            file_rows = connection.execute(
                "SELECT commit_hash, path FROM commit_files ORDER BY path"
            ).fetchall()
        files_by_commit: dict[str, list[str]] = {}
        for row in file_rows:
            files_by_commit.setdefault(str(row["commit_hash"]), []).append(str(row["path"]))
        current_paths = set(self.database.file_records())
        now = datetime.now(UTC)
        results: list[CommitEvidence] = []
        for row in commits:
            commit_hash = str(row["commit_hash"])
            changed = tuple(files_by_commit.get(commit_hash, []))
            overlap = tuple(sorted(anchor_paths.intersection(changed)))
            authored_at = datetime.fromisoformat(str(row["authored_at"]))
            if authored_at.tzinfo is None:
                authored_at = authored_at.replace(tzinfo=UTC)
            age_days = max(0.0, (now - authored_at).total_seconds() / 86_400)
            recency = 1.0 / (1.0 + age_days / 365.0)
            current_fraction = sum(path in current_paths for path in changed) / max(1, len(changed))
            lexical_score = lexical.get(commit_hash, 0.0)
            semantic_score = semantic.get(commit_hash, 0.0)
            anchor_score = min(1.0, len(overlap) / max(1, len(anchor_paths)))
            score = min(
                1.0,
                lexical_score * 0.45
                + semantic_score * 0.25
                + anchor_score * 0.2
                + recency * 0.05
                + current_fraction * 0.05,
            )
            strong_signal = lexical_score >= 0.15 or semantic_score >= 0.25 or bool(overlap)
            if score < minimum_score or not strong_signal:
                continue
            reasons: list[str] = []
            if lexical_score:
                reasons.append(f"history keyword relevance {lexical_score:.2f}")
            if semantic_score:
                reasons.append(f"history semantic relevance {semantic_score:.2f}")
            if overlap:
                reasons.append(f"changed anchor files: {', '.join(overlap)}")
            if current_fraction:
                reasons.append(f"{current_fraction:.0%} of changed files still exist")
            results.append(
                CommitEvidence(
                    commit_hash=commit_hash,
                    message=str(row["message"]),
                    authored_at=authored_at,
                    author_name=str(row["author_name"]),
                    changed_files=changed,
                    summary=str(row["summary"]),
                    score=score,
                    reasons=tuple(reasons),
                    lexical_score=lexical_score,
                    semantic_score=semantic_score,
                    anchor_overlap=overlap,
                )
            )
        results.sort(key=lambda result: (-result.score, -result.authored_at.timestamp()))
        return results[:limit]

    def co_changed_files(self, path: str, *, limit: int = 10) -> list[tuple[str, int]]:
        """Return files most frequently committed alongside *path*."""
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT CASE WHEN path_a = ? THEN path_b ELSE path_a END related, count
                FROM co_changes WHERE path_a = ? OR path_b = ?
                ORDER BY count DESC, related LIMIT ?
                """,
                (path, path, path, limit),
            ).fetchall()
        return [(str(row["related"]), int(row["count"])) for row in rows]

    def hotspots(self, *, limit: int = 20) -> list[tuple[str, int]]:
        """Return current files ordered by indexed commit frequency."""
        current = set(self.database.file_records())
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT path, COUNT(*) change_count FROM commit_files
                GROUP BY path ORDER BY change_count DESC, path
                """
            ).fetchall()
        return [
            (str(row["path"]), int(row["change_count"]))
            for row in rows
            if str(row["path"]) in current
        ][:limit]

    def _lexical_scores(self, task: str, *, limit: int) -> dict[str, float]:
        expression = fts_query(task)
        if not expression:
            return {}
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT commit_hash, bm25(commits_fts, 0.0, 3.0, 1.5, 2.0) rank
                FROM commits_fts WHERE commits_fts MATCH ? ORDER BY rank LIMIT ?
                """,
                (expression, limit),
            ).fetchall()
        strengths = {str(row["commit_hash"]): max(0.0, -float(row["rank"])) for row in rows}
        maximum = max(strengths.values(), default=1.0)
        return {commit_hash: score / maximum for commit_hash, score in strengths.items()}

    def _semantic_scores(self, task: str) -> dict[str, float]:
        if not self.provider:
            return {}
        try:
            query = self.provider.embed([task])[0]
        except Exception:
            return {}
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT unit_id, dimensions, vector FROM embeddings
                WHERE provider = ? AND unit_id LIKE 'commit:%'
                """,
                (self.provider.name,),
            ).fetchall()
        query_norm = math.sqrt(sum(value * value for value in query)) or 1.0
        scores: dict[str, float] = {}
        for row in rows:
            vector = _unpack(bytes(row["vector"]), int(row["dimensions"]))
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            similarity = sum(left * right for left, right in zip(query, vector, strict=True)) / (
                query_norm * norm
            )
            scores[str(row["unit_id"]).removeprefix("commit:")] = max(0.0, similarity)
        return scores
