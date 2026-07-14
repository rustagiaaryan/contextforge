from __future__ import annotations

from pathlib import Path

import pytest

from contextforge.config import ContextForgeConfig


def test_repository_config_loads_with_environment_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".contextforge.toml").write_text(
        "[contextforge]\ngraph_max_depth = 1\ngraph_max_nodes = 12\n"
    )
    monkeypatch.setenv("CONTEXTFORGE_GRAPH_MAX_NODES", "24")

    config = ContextForgeConfig.from_repository(tmp_path)

    assert config.graph_max_depth == 1
    assert config.graph_max_nodes == 24


def test_repository_config_rejects_unknown_fields(tmp_path: Path) -> None:
    (tmp_path / ".contextforge.toml").write_text("[contextforge]\nmagic = true\n")
    with pytest.raises(ValueError, match="magic"):
        ContextForgeConfig.from_repository(tmp_path)
