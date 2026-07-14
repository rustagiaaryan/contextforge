from __future__ import annotations

import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from contextforge.dashboard import create_dashboard

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"


def test_dashboard_serves_real_status_compile_and_graph_data(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    shutil.copytree(FIXTURE, repository, ignore=shutil.ignore_patterns(".contextforge"))
    client = TestClient(create_dashboard(repository))

    page = client.get("/")
    status = client.get("/api/status")
    compiled = client.post(
        "/api/compile",
        json={"task": "Mounted applications lose route prefixes.", "token_budget": 1200},
    )
    graph = client.get("/api/graph")

    assert page.status_code == 200
    assert "Repository Observatory" in page.text
    assert status.json()["files"] == 4
    assert compiled.status_code == 200
    assert compiled.json()["items"]
    assert graph.json()["nodes"]
    assert any(node["selected"] for node in graph.json()["nodes"])


def test_dashboard_validates_compile_budget(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    shutil.copytree(FIXTURE, repository, ignore=shutil.ignore_patterns(".contextforge"))
    client = TestClient(create_dashboard(repository))

    response = client.post("/api/compile", json={"task": "fix route", "token_budget": 100})

    assert response.status_code == 422
