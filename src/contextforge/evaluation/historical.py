"""Opt-in benchmark runner for pinned public GitHub bug-fix pull requests."""

from __future__ import annotations

import os
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse

from contextforge.evaluation.harness import ALL_CONFIGS, Evaluator
from contextforge.evaluation.models import (
    EvaluationConfig,
    HistoricalBenchmarkRun,
    HistoricalPatchSpec,
    TaskSpec,
)

SELECTION_POLICY = (
    "Four merged bug-fix PRs from each of Click, HTTPX, and Typer; descriptive titles, "
    "one to four changed Python files, and no documentation-only or dependency-only patches."
)


class HistoricalPatchBenchmark:
    """Materialize pre-fix snapshots, validate patch labels, and evaluate retrieval."""

    def __init__(self, manifest: Path) -> None:
        self.manifest = manifest.expanduser().resolve(strict=True)
        self.specs = self._load_manifest(self.manifest)

    def run(
        self,
        workspace: Path,
        *,
        configurations: tuple[EvaluationConfig, ...] = ALL_CONFIGS,
        top_k: int = 10,
        token_budget: int = 8_000,
        limit: int | None = None,
    ) -> HistoricalBenchmarkRun:
        """Download pinned public repositories and run the standard evaluator."""
        selected_specs = self.specs[:limit] if limit else self.specs
        root = workspace.expanduser().resolve()
        if root == Path(root.anchor):
            raise ValueError("Benchmark workspace cannot be a filesystem root")
        clones = root / "clones"
        snapshots = root / "snapshots"
        clones.mkdir(parents=True, exist_ok=True)
        snapshots.mkdir(parents=True, exist_ok=True)

        tasks: list[TaskSpec] = []
        repositories: set[str] = set()
        for spec in selected_specs:
            clone = self._ensure_clone(spec.repository_url, clones)
            snapshot = snapshots / spec.id
            self._prepare_snapshot(clone, snapshot, spec)
            repositories.add(spec.repository_url.removesuffix(".git"))
            tasks.append(
                TaskSpec(
                    id=spec.id,
                    repository=f"snapshots/{spec.id}",
                    task=spec.task,
                    gold_files=spec.gold_files,
                    metadata={
                        "kind": "historical_patch",
                        "source_url": spec.source_url,
                        "repository_url": spec.repository_url,
                        "base_commit": spec.base_commit,
                        "fix_commit": spec.fix_commit,
                    },
                )
            )

        dataset = root / "historical_tasks.jsonl"
        dataset.write_text(
            "".join(task.model_dump_json() + "\n" for task in tasks), encoding="utf-8"
        )
        evaluation = Evaluator(dataset).evaluate(
            configurations=configurations,
            top_k=top_k,
            token_budget=token_budget,
            measure_memory=False,
        )
        return HistoricalBenchmarkRun(
            manifest_name=self.manifest.name,
            manifest_sha256=sha256(self.manifest.read_bytes()).hexdigest(),
            task_count=len(tasks),
            repositories=tuple(sorted(repositories)),
            selection_policy=SELECTION_POLICY,
            evaluation=evaluation,
        )

    @staticmethod
    def _load_manifest(path: Path) -> tuple[HistoricalPatchSpec, ...]:
        specs: list[HistoricalPatchSpec] = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                specs.append(HistoricalPatchSpec.model_validate_json(line))
            except ValueError as error:
                raise ValueError(
                    f"Invalid historical manifest line {line_number}: {error}"
                ) from error
        if not specs:
            raise ValueError("Historical benchmark manifest contains no tasks")
        ids = [spec.id for spec in specs]
        if len(ids) != len(set(ids)):
            raise ValueError("Historical benchmark task IDs must be unique")
        return tuple(specs)

    def _ensure_clone(self, repository_url: str, clones: Path) -> Path:
        parsed = urlparse(repository_url)
        slug = parsed.path.strip("/").removesuffix(".git").replace("/", "--")
        destination = clones / slug
        # Shared snapshot clones need local blob objects. A partial/promisor clone
        # cannot reliably lend lazily downloaded blobs to another working tree.
        if destination.exists() and self._is_partial_clone(destination):
            shutil.rmtree(destination)
        if not destination.exists():
            self._git(
                "clone",
                "--quiet",
                "--no-checkout",
                repository_url,
                str(destination),
            )
        configured_url = self._git("-C", str(destination), "remote", "get-url", "origin")
        if configured_url != repository_url:
            raise ValueError(f"Cached clone origin mismatch for {destination.name}")
        return destination

    @staticmethod
    def _is_partial_clone(repository: Path) -> bool:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repository),
                "config",
                "--bool",
                "remote.origin.promisor",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=HistoricalPatchBenchmark._git_environment(),
            timeout=60,
        )
        return result.stdout.strip() == "true"

    def _prepare_snapshot(self, clone: Path, snapshot: Path, spec: HistoricalPatchSpec) -> None:
        for commit in (spec.base_commit, spec.fix_commit):
            if not self._has_commit(clone, commit):
                self._git("-C", str(clone), "fetch", "--quiet", "origin", commit)
            if not self._has_commit(clone, commit):
                raise ValueError(f"Pinned commit {commit} is unavailable for {spec.id}")
        ancestor = subprocess.run(
            [
                "git",
                "-C",
                str(clone),
                "merge-base",
                "--is-ancestor",
                spec.base_commit,
                spec.fix_commit,
            ],
            check=False,
            capture_output=True,
            text=True,
            env=self._git_environment(),
            timeout=60,
        )
        if ancestor.returncode != 0:
            raise ValueError(f"Base commit is not an ancestor of the fix for {spec.id}")
        changed = self._git(
            "-C",
            str(clone),
            "diff",
            "--name-only",
            spec.base_commit,
            spec.fix_commit,
            "--",
        ).splitlines()
        changed_python = tuple(
            sorted(path for path in changed if Path(path).suffix in {".py", ".pyi"})
        )
        if changed_python != tuple(sorted(spec.gold_files)):
            raise ValueError(
                f"Gold files for {spec.id} do not match its pinned patch: {changed_python}"
            )
        if snapshot.exists():
            shutil.rmtree(snapshot)
        self._git("clone", "--quiet", "--shared", "--no-checkout", str(clone), str(snapshot))
        # A clone sourced from another --no-checkout clone can have an index that
        # claims files are present while its worktree is empty. Force materialization.
        self._git(
            "-C",
            str(snapshot),
            "checkout",
            "--quiet",
            "--force",
            "--detach",
            spec.base_commit,
        )

    @staticmethod
    def _has_commit(repository: Path, commit: str) -> bool:
        result = subprocess.run(
            ["git", "-C", str(repository), "cat-file", "-e", f"{commit}^{{commit}}"],
            check=False,
            capture_output=True,
            text=True,
            env=HistoricalPatchBenchmark._git_environment(),
            timeout=60,
        )
        return result.returncode == 0

    @staticmethod
    def _git(*arguments: str) -> str:
        try:
            result = subprocess.run(
                ["git", *arguments],
                check=True,
                capture_output=True,
                text=True,
                env=HistoricalPatchBenchmark._git_environment(),
                timeout=600,
            )
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or error.stdout or "git command failed").strip()
            raise RuntimeError(detail) from error
        return result.stdout.strip()

    @staticmethod
    def _git_environment() -> dict[str, str]:
        environment = os.environ.copy()
        environment["GIT_TERMINAL_PROMPT"] = "0"
        environment["GIT_LFS_SKIP_SMUDGE"] = "1"
        return environment
