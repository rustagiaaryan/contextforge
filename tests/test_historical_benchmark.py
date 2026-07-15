from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from contextforge.evaluation.historical import HistoricalPatchBenchmark
from contextforge.evaluation.models import EvaluationConfig, HistoricalPatchSpec


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _repository_with_fix(tmp_path: Path) -> tuple[Path, str, str]:
    repository = tmp_path / "source"
    repository.mkdir()
    _git(repository, "init", "--quiet", "--initial-branch=main")
    _git(repository, "config", "user.name", "ContextForge Tests")
    _git(repository, "config", "user.email", "tests@example.invalid")
    source = repository / "src" / "module.py"
    source.parent.mkdir()
    source.write_text("def value():\n    return 1\n", encoding="utf-8")
    _git(repository, "add", "src/module.py")
    _git(repository, "commit", "--quiet", "-m", "initial")
    base = _git(repository, "rev-parse", "HEAD")
    source.write_text("def value():\n    return 2\n", encoding="utf-8")
    _git(repository, "commit", "--quiet", "-am", "fix value")
    fix = _git(repository, "rev-parse", "HEAD")
    return repository, base, fix


def _spec(base: str, fix: str, *, gold_files: tuple[str, ...]) -> HistoricalPatchSpec:
    return HistoricalPatchSpec(
        id="example-1-fix",
        repository_url="https://github.com/example/project.git",
        base_commit=base,
        fix_commit=fix,
        task="Fix the returned value in the example module.",
        gold_files=gold_files,
        source_url="https://github.com/example/project/pull/1",
    )


def test_historical_manifest_rejects_non_github_and_escaping_paths() -> None:
    with pytest.raises(ValidationError):
        HistoricalPatchSpec(
            id="unsafe-1",
            repository_url="ssh://example.com/project.git",
            base_commit="a" * 40,
            fix_commit="b" * 40,
            task="A sufficiently descriptive task.",
            gold_files=("../secret.py",),
            source_url="https://github.com/example/project/pull/1",
        )


def test_historical_snapshot_is_pre_fix_and_patch_labels_are_verified(tmp_path: Path) -> None:
    repository, base, fix = _repository_with_fix(tmp_path)
    spec = _spec(base, fix, gold_files=("src/module.py",))
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(spec.model_dump_json() + "\n", encoding="utf-8")
    benchmark = HistoricalPatchBenchmark(manifest)
    snapshot = tmp_path / "snapshot"

    assert benchmark._is_partial_clone(repository) is False
    benchmark._prepare_snapshot(repository, snapshot, spec)

    assert _git(snapshot, "rev-parse", "HEAD") == base
    assert (snapshot / "src" / "module.py").read_text(encoding="utf-8").endswith("return 1\n")

    invalid = _spec(base, fix, gold_files=("src/other.py",))
    with pytest.raises(ValueError, match="do not match"):
        benchmark._prepare_snapshot(repository, tmp_path / "invalid", invalid)


def test_historical_clone_cache_replaces_partial_clone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = _spec("a" * 40, "b" * 40, gold_files=("src/module.py",))
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(spec.model_dump_json() + "\n", encoding="utf-8")
    benchmark = HistoricalPatchBenchmark(manifest)
    clones = tmp_path / "clones"
    destination = clones / "example--project"
    destination.mkdir(parents=True)
    calls: list[tuple[str, ...]] = []

    monkeypatch.setattr(benchmark, "_is_partial_clone", lambda _path: True)

    def fake_git(*arguments: str) -> str:
        calls.append(arguments)
        if arguments[0] == "clone":
            Path(arguments[-1]).mkdir(parents=True)
            return ""
        return spec.repository_url

    monkeypatch.setattr(benchmark, "_git", fake_git)

    prepared = benchmark._ensure_clone(spec.repository_url, clones)

    assert prepared == destination
    assert calls[0][0] == "clone"


def test_historical_runner_evaluates_pre_fix_snapshot_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, base, fix = _repository_with_fix(tmp_path)
    spec = _spec(base, fix, gold_files=("src/module.py",))
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(spec.model_dump_json() + "\n", encoding="utf-8")
    benchmark = HistoricalPatchBenchmark(manifest)
    monkeypatch.setattr(
        benchmark,
        "_ensure_clone",
        lambda _repository_url, _clones: repository,
    )

    run = benchmark.run(
        tmp_path / "workspace",
        configurations=(EvaluationConfig.BM25, EvaluationConfig.FULL),
        top_k=3,
        token_budget=800,
    )

    assert run.task_count == 1
    assert run.manifest_sha256
    assert len(run.evaluation.results) == 2
    assert run.evaluation.memory_tracing_enabled is False
    assert run.evaluation.index_measurements[0].repository_source_tokens > 0
    assert run.evaluation.aggregates[-1].metrics.package_file_hit == 1.0
