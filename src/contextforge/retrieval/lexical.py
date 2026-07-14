"""Field-weighted SQLite FTS5/BM25 code retrieval."""

from __future__ import annotations

from contextforge.retrieval.models import Candidate, RetrievalSource
from contextforge.retrieval.text import fts_query, query_terms
from contextforge.storage import Database


class LexicalRetriever:
    """Search repository paths, symbols, signatures, docs, and code with BM25."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def search(self, query: str, *, limit: int = 30) -> list[Candidate]:
        """Return normalized BM25 candidates with matched-term provenance."""
        expression = fts_query(query)
        if not expression or limit < 1:
            return []
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT u.*, bm25(units_fts, 0.0, 3.0, 6.0, 5.0, 3.0, 2.5, 1.0) rank
                FROM units_fts
                JOIN units u ON u.unit_id = units_fts.unit_id
                WHERE units_fts MATCH ? AND u.node_type != 'module'
                ORDER BY rank, u.path, u.start_line
                LIMIT ?
                """,
                (expression, limit),
            ).fetchall()
        if not rows:
            return []
        strengths = [max(0.0, -float(row["rank"])) for row in rows]
        maximum = max(strengths) or 1.0
        terms = query_terms(query)
        candidates: list[Candidate] = []
        for row, strength in zip(rows, strengths, strict=True):
            unit = Database._row_to_unit(row)
            searchable = " ".join(
                [unit.path, unit.qualname, unit.signature, unit.docstring, unit.content]
            ).lower()
            matched = [term for term in terms if term in searchable]
            score = strength / maximum
            candidate = Candidate(unit=unit)
            candidate.add_signal(
                RetrievalSource.LEXICAL,
                score,
                f"BM25 matched {', '.join(matched[:6]) or 'indexed source text'}.",
                metadata={"bm25_raw": strength, "matched_terms": matched},
            )
            candidates.append(candidate)
        return candidates
