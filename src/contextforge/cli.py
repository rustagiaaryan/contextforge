"""ContextForge command-line interface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from contextforge import ContextForge, __version__

app = typer.Typer(
    help="Compile task-specific repository evidence for autonomous coding agents.",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)
graph_app = typer.Typer(
    help="Build and query portable, Tree-sitter repository knowledge graphs.",
    no_args_is_help=True,
)
skill_app = typer.Typer(help="Install ContextForge agent integrations.", no_args_is_help=True)
app.add_typer(graph_app, name="graph")
app.add_typer(skill_app, name="skill")
console = Console()


def version_callback(value: bool) -> None:
    """Print the installed version and exit."""
    if value:
        typer.echo(f"contextforge {__version__}")
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=version_callback, is_eager=True, help="Show version."),
    ] = None,
) -> None:
    """ContextForge command group."""


@app.command("index")
def index_repository(
    repository: Annotated[Path, typer.Argument(help="Local repository to index.")],
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit the machine-readable index report.")
    ] = False,
) -> None:
    """Incrementally index source, graph, embeddings, and local Git history."""
    report = ContextForge.open(repository).index()
    if json_output:
        typer.echo(report.model_dump_json(indent=2))
        return
    console.print(
        f"[green]Indexed[/green] {report.source.discovered_files} files, "
        f"{report.graph_nodes} graph nodes, {report.graph_edges} edges, and "
        f"{report.commits_indexed} commits in {report.elapsed_ms:.1f}ms."
    )
    if report.source.parse_errors:
        console.print(
            f"[yellow]{len(report.source.parse_errors)} parse errors were recorded.[/yellow]"
        )
    if not report.semantic_enabled:
        console.print(f"[yellow]Semantic retrieval disabled: {report.semantic_error}[/yellow]")


@app.command("status")
def index_status(
    repository: Annotated[Path, typer.Argument(help="Indexed local repository.")],
) -> None:
    """Print persistent index counts and parser errors as JSON."""
    typer.echo(ContextForge.open(repository).get_index_status().model_dump_json(indent=2))


@app.command("search")
def search_repository(
    repository: Annotated[Path, typer.Argument(help="Local repository to search.")],
    task: Annotated[str, typer.Option("--task", help="Task or issue search query.")],
    limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 20,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Run hybrid repository code search and show ranked provenance."""
    candidates = ContextForge.open(repository).search_code(task, limit=limit)
    if json_output:
        typer.echo(
            json.dumps(
                [candidate.model_dump(mode="json") for candidate in candidates],
                indent=2,
            )
        )
        return
    table = Table(title="ContextForge search")
    table.add_column("Score", justify="right")
    table.add_column("Source range")
    table.add_column("Retrieved by")
    table.add_column("Why")
    for candidate in candidates:
        table.add_row(
            f"{candidate.score:.3f}",
            f"{candidate.unit.path}:{candidate.unit.start_line}-{candidate.unit.end_line}\n"
            f"{candidate.unit.qualname}",
            ", ".join(source.value for source in candidate.retrieved_by),
            " ".join(candidate.reasons[:2]),
        )
    console.print(table)


@graph_app.command("build")
def build_repository_graph(
    repository: Annotated[Path, typer.Argument(help="Local repository to map.")],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output directory inside the repository."),
    ] = None,
    workers: Annotated[int, typer.Option("--workers", min=0, max=32)] = 0,
    cluster_backend: Annotated[
        str,
        typer.Option("--cluster", help="Community backend: auto, leiden, or networkx."),
    ] = "auto",
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Run detect, Tree-sitter extraction, graph build, clustering, and export."""
    from contextforge.codegraph import map_repository

    result = map_repository(
        repository,
        output_dir=output,
        workers=workers,
        cluster_backend=cluster_backend,
    )
    if json_output:
        typer.echo(json.dumps(result.to_dict(), indent=2, default=str))
        return
    console.print(
        f"[green]Mapped[/green] {result.files} files across "
        f"{', '.join(result.languages) or 'no languages'} into {result.nodes} nodes, "
        f"{result.edges} relationships, and {result.communities} communities."
    )
    console.print(f"Graph: [cyan]{result.graph_json}[/cyan]")
    console.print(f"Report: [cyan]{result.report_markdown}[/cyan]")
    console.print(f"Interactive view: [cyan]{result.graph_html}[/cyan]")
    if result.parse_warnings:
        console.print(
            f"[yellow]{len(result.parse_warnings)} parse warnings were recorded.[/yellow]"
        )


@graph_app.command("query")
def query_repository_graph(
    graph_file: Annotated[Path, typer.Argument(help="Generated graph.json artifact.")],
    question: Annotated[str, typer.Option("--question", "-q")],
    limit: Annotated[int, typer.Option("--limit", min=1, max=200)] = 25,
    hops: Annotated[int, typer.Option("--hops", min=0, max=3)] = 1,
) -> None:
    """Return a fuzzy-anchor, bounded subgraph for a natural-language question."""
    from contextforge.codegraph import load_graph, query_graph

    result = query_graph(load_graph(graph_file), question, limit=limit, hops=hops)
    typer.echo(json.dumps(result, indent=2))


@graph_app.command("path")
def trace_repository_graph_path(
    graph_file: Annotated[Path, typer.Argument(help="Generated graph.json artifact.")],
    source: Annotated[str, typer.Argument(help="Source node id, label, or qualified name.")],
    target: Annotated[str, typer.Argument(help="Target node id, label, or qualified name.")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Trace the shortest relationship path between two fuzzy-resolved concepts."""
    from contextforge.codegraph import load_graph, shortest_path

    result = shortest_path(load_graph(graph_file), source, target)
    if json_output:
        typer.echo(json.dumps(result, indent=2))
        return
    console.print(
        f"[bold]{result['source']['label']}[/bold] → "
        f"[bold]{result['target']['label']}[/bold] ({result['hops']} hops)"
    )
    for step in result["steps"]:
        arrow = "--" if step["direction"] == "outgoing" else "<--"
        console.print(
            f"  {step['source']} {arrow}{step['relation']}--> {step['target']} "
            f"[{step['confidence']}]"
        )


@graph_app.command("explain")
def explain_repository_graph_node(
    graph_file: Annotated[Path, typer.Argument(help="Generated graph.json artifact.")],
    node: Annotated[str, typer.Argument(help="Node id, label, or qualified name.")],
    limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 30,
) -> None:
    """Explain a concept and its strongest confidence-tagged relationships."""
    from contextforge.codegraph import explain_node, load_graph

    typer.echo(json.dumps(explain_node(load_graph(graph_file), node, limit=limit), indent=2))


@skill_app.command("install")
def install_agent_skill(
    repository: Annotated[Path, typer.Argument(help="Repository receiving the project skill.")],
    overwrite: Annotated[bool, typer.Option("--overwrite")] = False,
) -> None:
    """Install the ContextForge graph skill under the repository's .agents directory."""
    from contextforge.skill_install import install_graph_skill

    target = install_graph_skill(repository, overwrite=overwrite)
    console.print(f"[green]Installed[/green] ContextForge graph skill at [cyan]{target}[/cyan]")


@app.command("compile")
def compile_repository(
    repository: Annotated[Path, typer.Argument(help="Local repository to compile.")],
    task: Annotated[str | None, typer.Option("--task", help="Task or issue text.")] = None,
    task_file: Annotated[
        Path | None, typer.Option("--task-file", help="UTF-8 file containing task text.")
    ] = None,
    token_budget: Annotated[int, typer.Option("--token-budget", min=512)] = 8_000,
    output_format: Annotated[
        str, typer.Option("--format", help="Output format: markdown or json.")
    ] = "markdown",
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Compile a strict-budget evidence package for a task."""
    task_text = _read_task(task, task_file)
    result = ContextForge.open(repository).compile_context(
        task=task_text, token_budget=token_budget
    )
    normalized = output_format.lower()
    if normalized == "markdown":
        rendered = result.to_markdown()
    elif normalized == "json":
        rendered = result.to_json()
    else:
        raise typer.BadParameter("--format must be 'markdown' or 'json'")
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        console.print(f"[green]Wrote[/green] {output}")
    else:
        typer.echo(rendered, nl=False)


@app.command("mcp")
def serve_mcp() -> None:
    """Run the typed ContextForge MCP server over standard input/output."""
    from contextforge.mcp import mcp

    mcp.run(transport="stdio")


@app.command("evaluate")
def evaluate_repository_context(
    dataset: Annotated[Path, typer.Option("--dataset", help="Benchmark task JSONL file.")],
    token_budget: Annotated[int, typer.Option("--token-budget", min=512)] = 4_000,
    top_k: Annotated[int, typer.Option("--top-k", min=1, max=100)] = 10,
    limit: Annotated[int | None, typer.Option("--limit", min=1)] = None,
    run_ablations: Annotated[
        bool, typer.Option("--ablations", help="Also run all full-pipeline component ablations.")
    ] = False,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Evaluate baselines, retrieval stacks, and optional ablations on a JSONL dataset."""
    from contextforge.evaluation import Ablation, Evaluator

    run = Evaluator(dataset).evaluate(
        token_budget=token_budget,
        top_k=top_k,
        limit=limit,
        ablations=tuple(Ablation) if run_ablations else (),
    )
    rendered = run.model_dump_json(indent=2)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
        console.print(f"[green]Wrote[/green] {output}")
    else:
        typer.echo(rendered)


@app.command("evaluate-history")
def evaluate_historical_patches(
    manifest: Annotated[
        Path,
        typer.Option("--manifest", help="Pinned public historical-patch JSONL manifest."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", help="Cache and pre-fix snapshot directory."),
    ] = Path(".contextforge/historical-benchmark"),
    token_budget: Annotated[int, typer.Option("--token-budget", min=512)] = 8_000,
    top_k: Annotated[int, typer.Option("--top-k", min=1, max=100)] = 10,
    limit: Annotated[int | None, typer.Option("--limit", min=1)] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Evaluate pinned public fixes at their pre-fix commits (network opt-in)."""
    from contextforge.evaluation import HistoricalPatchBenchmark

    run = HistoricalPatchBenchmark(manifest).run(
        workspace,
        token_budget=token_budget,
        top_k=top_k,
        limit=limit,
    )
    rendered = run.model_dump_json(indent=2)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
        console.print(f"[green]Wrote[/green] {output}")
    else:
        typer.echo(rendered)


@app.command("dashboard")
def serve_dashboard(
    repository: Annotated[Path, typer.Argument(help="Indexed local repository.")],
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", min=1, max=65_535)] = 8765,
    open_browser: Annotated[bool, typer.Option("--open")] = False,
) -> None:
    """Run the real-output repository observatory on a local HTTP endpoint."""
    import webbrowser

    import uvicorn

    from contextforge.dashboard import create_dashboard

    if open_browser:
        webbrowser.open(f"http://{host}:{port}")
    uvicorn.run(create_dashboard(repository), host=host, port=port, log_level="warning")


def _read_task(task: str | None, task_file: Path | None) -> str:
    if bool(task) == bool(task_file):
        raise typer.BadParameter("Provide exactly one of --task or --task-file")
    if task_file:
        try:
            value = task_file.read_text(encoding="utf-8")
        except OSError as error:
            raise typer.BadParameter(f"Cannot read task file: {error}") from error
    else:
        value = task or ""
    if not value.strip():
        raise typer.BadParameter("Task text cannot be empty")
    return value.strip()


if __name__ == "__main__":
    app()
