"""Parser extension protocol."""

from pathlib import Path
from typing import Protocol

from contextforge.models import ParsedFile


class LanguageParser(Protocol):
    """Contract implemented by language-specific source parsers."""

    extensions: frozenset[str]

    def parse(self, repository: Path, path: Path) -> ParsedFile:
        """Parse *path* relative to *repository* without executing it."""
