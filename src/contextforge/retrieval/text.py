"""Shared query tokenization and lexical helpers."""

from __future__ import annotations

import re

TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,}|\d{2,}")

STOP_WORDS = frozenset(
    {
        "about",
        "after",
        "also",
        "and",
        "are",
        "because",
        "before",
        "but",
        "can",
        "could",
        "does",
        "file",
        "fix",
        "for",
        "from",
        "has",
        "have",
        "into",
        "issue",
        "not",
        "should",
        "that",
        "the",
        "their",
        "then",
        "this",
        "through",
        "when",
        "where",
        "which",
        "with",
    }
)


def query_terms(text: str, *, limit: int = 24) -> tuple[str, ...]:
    """Return stable, distinct query terms suitable for FTS and symbol search."""
    terms: list[str] = []
    seen: set[str] = set()
    for match in TOKEN_PATTERN.finditer(text):
        term = match.group(0).lower()
        if term in STOP_WORDS or term in seen:
            continue
        seen.add(term)
        terms.append(term)
        if len(terms) >= limit:
            break
    return tuple(terms)


def fts_query(text: str) -> str:
    """Build a safe FTS disjunction from plain task text."""
    return " OR ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in query_terms(text))
