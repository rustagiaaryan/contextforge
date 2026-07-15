from __future__ import annotations

import json
from pathlib import Path

from tree_sitter import Parser

from contextforge.codegraph import (
    explain_node,
    load_graph,
    map_repository,
    query_graph,
    shortest_path,
)
from contextforge.codegraph.build import build_graph
from contextforge.codegraph.detect import collect_files
from contextforge.codegraph.extract import LANGUAGES, _load_language, extract_file
from contextforge.codegraph.models import ConfidenceLabel, Extraction
from contextforge.codegraph.validate import validate_extraction

FIXTURE = Path(__file__).parent / "fixtures" / "multilang_repo"


def test_all_bundled_tree_sitter_grammars_load() -> None:
    grammars = {(spec.module, spec.loader): spec for spec in LANGUAGES.values()}
    for spec in grammars.values():
        Parser(_load_language(spec)).parse(b"")
    assert len(grammars) == 26


def test_collect_and_extract_multiple_tree_sitter_languages() -> None:
    files = collect_files(FIXTURE)
    assert [path.suffix for path in files] == [".py", ".py", ".ts", ".go"]

    python = extract_file(FIXTURE, FIXTURE / "services" / "router.py")
    typescript = extract_file(FIXTURE, FIXTURE / "web" / "client.ts")
    go = extract_file(FIXTURE, FIXTURE / "worker" / "main.go")

    assert {node["label"] for node in python["nodes"]} >= {"Mount", "resolve"}
    assert {node["label"] for node in typescript["nodes"]} >= {"RouteClient", "combine"}
    assert {node["label"] for node in go["nodes"]} >= {"Run"}
    assert any(edge.get("target_ref") == "join_path" for edge in python["edges"])
    assert any(edge["relation"] == "imports" for edge in go["edges"])
    validate_extraction(python)


def test_build_graph_preserves_confidence_and_resolves_symbols() -> None:
    extractions = [extract_file(FIXTURE, path) for path in collect_files(FIXTURE)]
    graph = build_graph(extractions)
    resolved_calls = [
        (source, target, attributes)
        for source, target, attributes in graph.edges(data=True)
        if attributes["relation"] == "calls" and graph.nodes[target]["label"] == "join_path"
    ]
    assert resolved_calls
    assert resolved_calls[0][2]["confidence"] == ConfidenceLabel.INFERRED.value
    assert any(
        attributes["confidence"] == ConfidenceLabel.EXTRACTED.value
        for _, _, attributes in graph.edges(data=True)
        if attributes["relation"] == "defines"
    )


def test_ambiguous_symbol_resolution_is_explicit() -> None:
    extraction: Extraction = {
        "path": "sample.py",
        "language": "python",
        "nodes": [
            {
                "id": "file:sample.py",
                "label": "sample.py",
                "kind": "file",
                "source_file": "sample.py",
                "source_location": "L1",
                "language": "python",
            },
            {
                "id": "function:sample.py:first.run",
                "label": "run",
                "kind": "function",
                "source_file": "sample.py",
                "source_location": "L1",
                "language": "python",
            },
            {
                "id": "function:sample.py:second.run",
                "label": "run",
                "kind": "function",
                "source_file": "sample.py",
                "source_location": "L4",
                "language": "python",
            },
        ],
        "edges": [
            {
                "source": "file:sample.py",
                "target": "",
                "target_ref": "run",
                "relation": "calls",
                "confidence": "INFERRED",
                "source_location": "L8",
            }
        ],
        "parse_errors": [],
    }
    graph = build_graph([extraction])
    calls = list(graph.out_edges("file:sample.py", data=True))
    assert len(calls) == 2
    assert {edge[2]["confidence"] for edge in calls} == {"AMBIGUOUS"}


def test_pipeline_exports_real_queryable_artifacts(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    for source in collect_files(FIXTURE):
        destination = repository / source.relative_to(FIXTURE)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())

    result = map_repository(
        repository,
        output_dir=repository / "contextforge-out",
        workers=2,
        cluster_backend="networkx",
    )
    assert result.files == 4
    assert result.languages == ("go", "python", "typescript")
    assert result.nodes > result.files
    assert result.edges > 0
    assert result.communities > 0
    assert result.graph_json.is_file()
    assert "Central concepts" in result.report_markdown.read_text(encoding="utf-8")
    assert "Interactive repository graph" in result.graph_html.read_text(encoding="utf-8")

    payload = json.loads(result.graph_json.read_text(encoding="utf-8"))
    assert payload["generator"] == "ContextForge"
    graph = load_graph(result.graph_json)
    scoped = query_graph(graph, "mounted route resolution", limit=10)
    assert any(anchor["label"] == "Mount" for anchor in scoped["anchors"])
    explanation = explain_node(graph, "Mount")
    assert explanation["node"]["label"] == "Mount"
    path = shortest_path(graph, "Mount", "join_path")
    assert path["hops"] >= 1
    assert any(step["relation"] == "calls" for step in path["steps"])
