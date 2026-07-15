# ruff: noqa: E501
"""JSON, Markdown, and interactive HTML graph artifact exports."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, cast

from contextforge.codegraph.models import CodeGraph, GraphSummary
from contextforge.codegraph.report import render_report


def graph_payload(
    graph: CodeGraph,
    summary: GraphSummary,
    *,
    repository_name: str,
    timings: dict[str, float],
) -> dict[str, Any]:
    """Return the stable, portable JSON representation of a graph."""
    nodes = []
    node_records = cast(list[tuple[str, dict[str, Any]]], list(graph.nodes(data=True)))
    for node_id, attributes in sorted(node_records, key=lambda item: item[0]):
        record = dict(attributes)
        record["id"] = str(node_id)
        nodes.append(record)
    edges = []
    for source, target, key, attributes in sorted(
        graph.edges(data=True, keys=True),
        key=lambda item: (str(item[0]), str(item[1]), str(item[2])),
    ):
        record = dict(attributes)
        record.update(source=str(source), target=str(target), key=str(key))
        edges.append(record)
    return {
        "schema_version": 1,
        "generator": "ContextForge",
        "repository": repository_name,
        "metadata": {**dict(graph.graph), "timings_ms": timings},
        "summary": summary,
        "nodes": nodes,
        "edges": edges,
    }


def write_artifacts(
    repository: Path,
    output_dir: Path,
    graph: CodeGraph,
    summary: GraphSummary,
    *,
    timings: dict[str, float],
) -> tuple[Path, Path, Path]:
    """Write graph JSON, Markdown report, and standalone interactive HTML."""
    root = repository.resolve(strict=True)
    target = output_dir.expanduser().resolve()
    if not target.is_relative_to(root):
        raise ValueError("Graph output directory must remain inside the repository")
    target.mkdir(parents=True, exist_ok=True)
    payload = graph_payload(
        graph,
        summary,
        repository_name=root.name,
        timings=timings,
    )
    json_path = target / "graph.json"
    report_path = target / "GRAPH_REPORT.md"
    html_path = target / "graph.html"
    _atomic_write(json_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    _atomic_write(report_path, render_report(root.name, summary, timings=timings))
    _atomic_write(html_path, render_graph_html(payload))
    return json_path, report_path, html_path


def render_graph_html(payload: dict[str, Any]) -> str:
    """Render a dependency-free, interactive SVG repository graph."""
    visual = _visual_payload(payload)
    encoded = json.dumps(visual, separators=(",", ":")).replace("<", "\\u003c")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_html_text(str(payload["repository"]))} · ContextForge graph</title>
<style>
:root{{--ink:#e8edf7;--muted:#8994a8;--panel:#111827;--line:#293548;--accent:#67e8f9}}
*{{box-sizing:border-box}} body{{margin:0;background:#070b12;color:var(--ink);font:14px Inter,ui-sans-serif,system-ui}}
header{{display:flex;gap:18px;align-items:center;padding:18px 22px;border-bottom:1px solid #1e293b;background:#0b111c}}
h1{{font-size:18px;margin:0}} .pill{{padding:5px 9px;border:1px solid #334155;border-radius:99px;color:var(--muted)}}
main{{display:grid;grid-template-columns:minmax(0,1fr) 320px;height:calc(100vh - 69px)}}
#stage{{position:relative;overflow:hidden}} svg{{width:100%;height:100%;cursor:grab}} svg:active{{cursor:grabbing}}
aside{{border-left:1px solid #1e293b;background:var(--panel);padding:18px;overflow:auto}}
input,select{{width:100%;margin:0 0 12px;padding:10px 12px;color:var(--ink);background:#0b1220;border:1px solid #334155;border-radius:8px}}
.edge{{stroke:var(--line);stroke-opacity:.58}} .node{{stroke:#07111d;stroke-width:1.5;cursor:pointer;transition:.15s}}
.node:hover{{stroke:#fff;stroke-width:2.5}} .label{{fill:#bac4d6;font-size:10px;pointer-events:none}}
.dim{{opacity:.08}} .selected{{stroke:#fff;stroke-width:3}} dt{{color:var(--muted);margin-top:12px}} dd{{margin:3px 0;overflow-wrap:anywhere}}
#legend{{display:flex;flex-wrap:wrap;gap:7px;margin:10px 0 18px}} .legend{{font-size:11px;color:var(--muted)}}
.dot{{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px}} .notice{{color:var(--muted);font-size:12px;line-height:1.5}}
</style></head>
<body><header><h1>{_html_text(str(payload["repository"]))}</h1><span class="pill">{len(visual["nodes"])} nodes shown</span><span class="pill">{len(visual["edges"])} edges</span><span class="pill">local graph artifact</span></header>
<main><section id="stage"><svg id="graph" viewBox="0 0 1200 800" aria-label="Interactive repository graph"></svg></section>
<aside><input id="search" type="search" placeholder="Search nodes, files, or symbols…"><select id="community"><option value="">All communities</option></select><div id="legend"></div><div id="details"><p class="notice">Select a node to inspect its source, community, and relationships. Search dims non-matching nodes.</p></div></aside></main>
<script>
const data={encoded}; const svg=document.getElementById('graph'); const NS='http://www.w3.org/2000/svg';
const palette=['#67e8f9','#a78bfa','#f472b6','#fbbf24','#34d399','#fb7185','#60a5fa','#c084fc','#f97316','#22d3ee'];
const byId=new Map(data.nodes.map(n=>[n.id,n])); const adjacency=new Map(data.nodes.map(n=>[n.id,new Set()]));
data.edges.forEach(e=>{{adjacency.get(e.source)?.add(e.target);adjacency.get(e.target)?.add(e.source)}});
const edgeLayer=document.createElementNS(NS,'g'), nodeLayer=document.createElementNS(NS,'g'), labelLayer=document.createElementNS(NS,'g'); svg.append(edgeLayer,nodeLayer,labelLayer);
data.edges.forEach(e=>{{const a=byId.get(e.source),b=byId.get(e.target);if(!a||!b)return;const line=document.createElementNS(NS,'line');line.setAttribute('x1',a.x);line.setAttribute('y1',a.y);line.setAttribute('x2',b.x);line.setAttribute('y2',b.y);line.setAttribute('class','edge');line.dataset.source=e.source;line.dataset.target=e.target;line.setAttribute('stroke-width',Math.max(.5,Number(e.weight||.7)));edgeLayer.append(line)}});
const degree=new Map(data.nodes.map(n=>[n.id,adjacency.get(n.id).size]));
data.nodes.forEach(n=>{{const c=document.createElementNS(NS,'circle');c.setAttribute('cx',n.x);c.setAttribute('cy',n.y);c.setAttribute('r',Math.min(11,4+Math.sqrt(degree.get(n.id)||0)));c.setAttribute('fill',palette[Math.abs(Number(n.community)||0)%palette.length]);c.setAttribute('class','node');c.dataset.id=n.id;c.addEventListener('click',()=>selectNode(n.id));nodeLayer.append(c);if((degree.get(n.id)||0)>=data.labelThreshold){{const t=document.createElementNS(NS,'text');t.setAttribute('x',n.x+9);t.setAttribute('y',n.y+3);t.setAttribute('class','label');t.textContent=n.label;labelLayer.append(t)}}}});
const communities=[...new Set(data.nodes.map(n=>Number(n.community)||0))].sort((a,b)=>a-b);const select=document.getElementById('community'),legend=document.getElementById('legend');communities.forEach(c=>{{const o=document.createElement('option');o.value=c;o.textContent='Community '+c;select.append(o);const l=document.createElement('span');l.className='legend';l.innerHTML='<i class="dot" style="background:'+palette[Math.abs(c)%palette.length]+'"></i>'+c;legend.append(l)}});
function applyFilter(){{const q=document.getElementById('search').value.toLowerCase(),community=select.value;document.querySelectorAll('.node').forEach(el=>{{const n=byId.get(el.dataset.id);const match=(!q||(n.label+' '+n.source_file+' '+(n.qualname||'')).toLowerCase().includes(q))&&(!community||String(n.community)===community);el.classList.toggle('dim',!match)}})}}
document.getElementById('search').addEventListener('input',applyFilter);select.addEventListener('change',applyFilter);
function selectNode(id){{document.querySelectorAll('.node').forEach(el=>el.classList.toggle('selected',el.dataset.id===id));const n=byId.get(id),links=data.edges.filter(e=>e.source===id||e.target===id);document.getElementById('details').innerHTML='<h2>'+escapeHtml(n.label)+'</h2><dl><dt>Kind</dt><dd>'+escapeHtml(n.kind)+'</dd><dt>Source</dt><dd>'+escapeHtml(n.source_file||'external')+' '+escapeHtml(n.source_location||'')+'</dd><dt>Community</dt><dd>'+n.community+'</dd><dt>Relationships</dt><dd>'+links.slice(0,30).map(e=>escapeHtml(e.relation)+' '+escapeHtml(e.source===id?(byId.get(e.target)?.label||e.target):(byId.get(e.source)?.label||e.source))+' <small>['+escapeHtml(e.confidence)+']</small>').join('<br>')+'</dd></dl>'}}
function escapeHtml(v){{const d=document.createElement('div');d.textContent=String(v);return d.innerHTML}}
let box={{x:0,y:0,w:1200,h:800}},drag=null;svg.addEventListener('wheel',e=>{{e.preventDefault();const f=e.deltaY>0?1.12:.88;box.w*=f;box.h*=f;svg.setAttribute('viewBox',`${{box.x}} ${{box.y}} ${{box.w}} ${{box.h}}`)}},{{passive:false}});svg.addEventListener('pointerdown',e=>drag={{x:e.clientX,y:e.clientY,bx:box.x,by:box.y}});svg.addEventListener('pointermove',e=>{{if(!drag)return;box.x=drag.bx-(e.clientX-drag.x)*box.w/svg.clientWidth;box.y=drag.by-(e.clientY-drag.y)*box.h/svg.clientHeight;svg.setAttribute('viewBox',`${{box.x}} ${{box.y}} ${{box.w}} ${{box.h}}`)}});svg.addEventListener('pointerup',()=>drag=null);svg.addEventListener('pointerleave',()=>drag=null);
</script></body></html>"""


def _visual_payload(payload: dict[str, Any], *, limit: int = 700) -> dict[str, Any]:
    nodes = list(payload["nodes"])
    edges = list(payload["edges"])
    degree: dict[str, int] = {str(node["id"]): 0 for node in nodes}
    for edge in edges:
        if str(edge["source"]) in degree:
            degree[str(edge["source"])] += 1
        if str(edge["target"]) in degree:
            degree[str(edge["target"])] += 1
    selected = sorted(nodes, key=lambda node: (-degree[str(node["id"])], str(node["id"])))[:limit]
    selected_ids = {str(node["id"]) for node in selected}
    visible_edges = [
        edge
        for edge in edges
        if str(edge["source"]) in selected_ids and str(edge["target"]) in selected_ids
    ]
    grouped: dict[int, list[dict[str, Any]]] = {}
    for node in selected:
        grouped.setdefault(int(node.get("community", 0)), []).append(node)
    community_count = max(1, len(grouped))
    positioned: list[dict[str, Any]] = []
    for group_index, (community, members) in enumerate(sorted(grouped.items())):
        center_angle = 2 * math.pi * group_index / community_count
        center_x = 600 + 330 * math.cos(center_angle)
        center_y = 400 + 250 * math.sin(center_angle)
        radius = min(150.0, 24.0 + 12.0 * math.sqrt(len(members)))
        for member_index, node in enumerate(sorted(members, key=lambda item: str(item["id"]))):
            angle = 2 * math.pi * member_index / max(1, len(members))
            record = dict(node)
            record["community"] = community
            record["x"] = round(center_x + radius * math.cos(angle), 2)
            record["y"] = round(center_y + radius * math.sin(angle), 2)
            positioned.append(record)
    degrees = sorted(degree.values(), reverse=True)
    threshold = degrees[min(len(degrees) - 1, max(0, len(degrees) // 12))] if degrees else 0
    return {"nodes": positioned, "edges": visible_edges, "labelThreshold": threshold}


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def _html_text(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
