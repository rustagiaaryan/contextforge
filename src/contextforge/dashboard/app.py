"""FastAPI dashboard over real ContextForge index and compilation output."""

from __future__ import annotations

import asyncio
import json
from importlib.resources import files
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from contextforge import ContextForge
from contextforge.context import EvidencePackage


class CompileRequest(BaseModel):
    """Validated dashboard compilation request."""

    model_config = ConfigDict(str_strip_whitespace=True)

    task: str = Field(min_length=3, max_length=20_000)
    token_budget: int = Field(default=4_000, ge=512, le=200_000)


class DashboardState:
    """Process-local latest package used only for visualization overlays."""

    def __init__(self, engine: ContextForge) -> None:
        self.engine = engine
        self.latest: EvidencePackage | None = None


def _asset(name: str) -> str:
    return files("contextforge.dashboard.static").joinpath(name).read_text(encoding="utf-8")


def create_dashboard(repository: str | Path) -> FastAPI:
    """Create a loopback-oriented dashboard for one selected repository."""
    engine = ContextForge.open(repository)
    if not engine.get_index_status().indexed:
        engine.index()
    state = DashboardState(engine)
    app = FastAPI(
        title="ContextForge Repository Observatory",
        description="Inspect real adaptive context compilation traces.",
        docs_url="/api/docs",
        redoc_url=None,
    )

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def dashboard() -> HTMLResponse:
        return HTMLResponse(_asset("index.html"))

    @app.get("/assets/styles.css", include_in_schema=False)
    async def styles() -> Response:
        return Response(_asset("styles.css"), media_type="text/css")

    @app.get("/assets/dashboard.js", include_in_schema=False)
    async def script() -> Response:
        return Response(_asset("dashboard.js"), media_type="text/javascript")

    @app.get("/api/status")
    async def status() -> dict[str, object]:
        """Return persistent repository index status."""
        return engine.get_index_status().model_dump(mode="json")

    @app.post("/api/compile")
    async def compile_context(request: CompileRequest) -> dict[str, object]:
        """Compile real repository evidence without blocking the event loop."""
        try:
            package = await asyncio.to_thread(
                engine.compile_context,
                task=request.task,
                token_budget=request.token_budget,
            )
        except (OSError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        state.latest = package
        return package.model_dump(mode="json")

    @app.get("/api/graph")
    async def graph(limit: int = Query(default=180, ge=1, le=500)) -> dict[str, object]:
        """Return a bounded graph with latest anchor/selection overlay flags."""
        selected_ids: set[str] = set()
        anchor_ids: set[str] = set()
        if state.latest:
            anchor_ids.update(state.latest.initial_anchor_ids)
            selected_ids.update(
                item.source_pointer.removeprefix("contextforge://unit/")
                for item in state.latest.items
            )
        with engine.database.connection() as connection:
            node_rows = connection.execute(
                """
                SELECT * FROM graph_nodes
                ORDER BY CASE node_type
                    WHEN 'repository' THEN 0 WHEN 'directory' THEN 1
                    WHEN 'file' THEN 2 WHEN 'module' THEN 3 ELSE 4 END,
                    label LIMIT ?
                """,
                (limit,),
            ).fetchall()
            node_ids = {str(row["node_id"]) for row in node_rows}
            edge_rows = connection.execute(
                "SELECT * FROM graph_edges ORDER BY edge_type, source_id, target_id"
            ).fetchall()
        nodes = [
            {
                "id": str(row["node_id"]),
                "type": str(row["node_type"]),
                "path": str(row["path"]) if row["path"] else None,
                "label": str(row["label"]),
                "selected": str(row["node_id"]) in selected_ids,
                "anchor": str(row["node_id"]) in anchor_ids,
                "metadata": json.loads(str(row["metadata_json"])),
            }
            for row in node_rows
        ]
        edges = [
            {
                "source": str(row["source_id"]),
                "target": str(row["target_id"]),
                "type": str(row["edge_type"]),
                "confidence": float(row["confidence"]),
            }
            for row in edge_rows
            if str(row["source_id"]) in node_ids and str(row["target_id"]) in node_ids
        ]
        return {"nodes": nodes, "edges": edges}

    return app
