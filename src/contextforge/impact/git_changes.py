"""Bounded Git diff reading for change impact analysis."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


class ChangedRange(BaseModel):
    """A changed line range on the new side of a Git diff."""

    model_config = ConfigDict(frozen=True)

    path: str
    start_line: int = Field(ge=0)
    end_line: int = Field(ge=0)
    status: str
    old_path: str | None = None


class GitChangeReader:
    """Read local changes without invoking a shell or prompting for credentials."""

    def __init__(self, repository: Path) -> None:
        self.repository = repository.resolve(strict=True)

    def read(self, base: str | None = None) -> tuple[ChangedRange, ...]:
        """Return committed, staged, working-tree, and untracked changes."""
        try:
            is_repository = self._run("rev-parse", "--is-inside-work-tree").strip() == "true"
        except subprocess.CalledProcessError as error:
            raise ValueError(f"not a Git repository: {self.repository}") from error
        if not is_repository:
            raise ValueError(f"not a Git repository: {self.repository}")
        outputs: list[str] = []
        if base:
            try:
                self._run("rev-parse", "--verify", f"{base}^{{commit}}")
            except subprocess.CalledProcessError as error:
                raise ValueError(f"invalid Git revision: {base}") from error
            outputs.append(
                self._run(
                    "diff",
                    "--relative",
                    "--unified=0",
                    "--find-renames",
                    f"{base}...HEAD",
                    "--",
                )
            )
        outputs.append(
            self._run(
                "diff",
                "--relative",
                "--unified=0",
                "--find-renames",
                "HEAD",
                "--",
            )
        )
        changes = [change for output in outputs for change in self.parse_diff(output)]
        untracked = self._run("ls-files", "--others", "--exclude-standard", "-z")
        for relative_path in filter(None, untracked.split("\0")):
            path = self.repository / relative_path
            line_count = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
            changes.append(
                ChangedRange(
                    path=relative_path,
                    start_line=1,
                    end_line=max(1, line_count),
                    status="untracked",
                )
            )
        unique = {self._key(change): change for change in changes}
        return tuple(sorted(unique.values(), key=self._key))

    def _run(self, *arguments: str) -> str:
        environment = os.environ.copy()
        environment.update({"GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"})
        try:
            completed = subprocess.run(
                ["git", "-c", "core.quotepath=false", *arguments],
                cwd=self.repository,
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
                env=environment,
            )
        except subprocess.CalledProcessError:
            raise
        return completed.stdout

    @staticmethod
    def parse_diff(output: str) -> tuple[ChangedRange, ...]:
        """Parse zero-context unified diff text into new-side line ranges."""
        changes: list[ChangedRange] = []
        sections = re.split(r"(?m)^diff --git ", output)
        for section in sections[1:]:
            lines = section.splitlines()
            old_path: str | None = None
            path: str | None = None
            status = "modified"
            for line in lines:
                if line.startswith("new file mode "):
                    status = "added"
                elif line.startswith("deleted file mode "):
                    status = "deleted"
                elif line.startswith("rename from "):
                    old_path = line.removeprefix("rename from ")
                    status = "renamed"
                elif line.startswith("rename to "):
                    path = line.removeprefix("rename to ")
                    status = "renamed"
                elif line.startswith("+++ b/"):
                    path = line.removeprefix("+++ b/")
            if path is None:
                header = lines[0] if lines else ""
                match = re.match(r"a/.+ b/(.+)$", header)
                path = match.group(1) if match else None
            if path is None:
                continue
            if status == "deleted":
                changes.append(
                    ChangedRange(
                        path=old_path or path,
                        start_line=0,
                        end_line=0,
                        status=status,
                        old_path=old_path,
                    )
                )
                continue
            hunks = [match for line in lines if (match := _HUNK.match(line))]
            if not hunks and status == "renamed":
                changes.append(
                    ChangedRange(
                        path=path,
                        start_line=1,
                        end_line=1,
                        status=status,
                        old_path=old_path,
                    )
                )
            for match in hunks:
                start = int(match.group(1))
                count = int(match.group(2) or "1")
                changes.append(
                    ChangedRange(
                        path=path,
                        start_line=start,
                        end_line=start + max(1, count) - 1,
                        status=status,
                        old_path=old_path,
                    )
                )
        unique = {GitChangeReader._key(change): change for change in changes}
        return tuple(sorted(unique.values(), key=GitChangeReader._key))

    @staticmethod
    def _key(change: ChangedRange) -> tuple[str, int, int, str, str]:
        return (
            change.path,
            change.start_line,
            change.end_line,
            change.status,
            change.old_path or "",
        )
