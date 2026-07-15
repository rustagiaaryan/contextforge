"""Side-effect-bounded orchestration for repository graph artifacts."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path

from contextforge.codegraph.analyze import analyze_graph
from contextforge.codegraph.build import build_graph
from contextforge.codegraph.cluster import cluster_graph
from contextforge.codegraph.detect import collect_files
from contextforge.codegraph.export import write_artifacts
from contextforge.codegraph.extract import extract_file
from contextforge.codegraph.models import Extraction


@dataclass(frozen=True)
class GraphBuildResult:
    """Measured result and portable artifact locations for one graph build."""

    repository: str
    files: int
    languages: tuple[str, ...]
    nodes: int
    edges: int
    communities: int
    parse_warnings: tuple[str, ...]
    timings_ms: dict[str, float]
    graph_json: Path
    report_markdown: Path
    graph_html: Path

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready result without machine-specific absolute paths."""
        data = asdict(self)
        data["graph_json"] = self.graph_json.name
        data["report_markdown"] = self.report_markdown.name
        data["graph_html"] = self.graph_html.name
        return data


def map_repository(
    repository: Path | str,
    *,
    output_dir: Path | None = None,
    workers: int = 0,
    cluster_backend: str = "auto",
) -> GraphBuildResult:
    """Run detect → extract → build → cluster → analyze → report/export."""
    root = Path(repository).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(f"Repository path is not a directory: {root}")
    if output_dir is None:
        target = root / "contextforge-out"
    else:
        target = output_dir if output_dir.is_absolute() else root / output_dir
    timings: dict[str, float] = {}

    started = time.perf_counter()
    files = collect_files(root)
    timings["detect"] = _elapsed(started)

    started = time.perf_counter()
    extractions: list[Extraction] = []
    failures: list[str] = []
    worker_count = workers if workers > 0 else min(8, max(1, len(files)))
    with ThreadPoolExecutor(
        max_workers=worker_count,
        thread_name_prefix="contextforge-graph",
    ) as pool:
        pending = {pool.submit(extract_file, root, path): path for path in files}
        for future in as_completed(pending):
            path = pending[future]
            try:
                extractions.append(future.result())
            except Exception as error:
                relative = path.relative_to(root).as_posix()
                failures.append(f"{relative}: {type(error).__name__}: {error}")
    extractions.sort(key=lambda extraction: extraction["path"])
    timings["extract"] = _elapsed(started)

    started = time.perf_counter()
    graph = build_graph(extractions)
    timings["build"] = _elapsed(started)

    started = time.perf_counter()
    cluster_graph(graph, backend=cluster_backend)
    timings["cluster"] = _elapsed(started)

    started = time.perf_counter()
    summary = analyze_graph(graph)
    timings["analyze"] = _elapsed(started)

    started = time.perf_counter()
    graph_json, report_markdown, graph_html = write_artifacts(
        root,
        target,
        graph,
        summary,
        timings=timings,
    )
    timings["export"] = _elapsed(started)
    parse_warnings = sorted(
        [*failures]
        + [
            f"{extraction['path']}: {warning}"
            for extraction in extractions
            for warning in extraction["parse_errors"]
        ]
    )
    return GraphBuildResult(
        repository=root.name,
        files=len(extractions),
        languages=tuple(sorted({extraction["language"] for extraction in extractions})),
        nodes=graph.number_of_nodes(),
        edges=graph.number_of_edges(),
        communities=int(graph.graph.get("community_count", 0)),
        parse_warnings=tuple(parse_warnings),
        timings_ms=timings,
        graph_json=graph_json,
        report_markdown=report_markdown,
        graph_html=graph_html,
    )


def _elapsed(started: float) -> float:
    return round((time.perf_counter() - started) * 1000.0, 3)
