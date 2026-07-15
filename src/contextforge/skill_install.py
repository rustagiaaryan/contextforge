"""Safe project-scoped installation of the bundled ContextForge graph skill."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path


def install_graph_skill(repository: Path | str, *, overwrite: bool = False) -> Path:
    """Install the bundled graph skill under ``.agents/skills`` in a repository."""
    root = Path(repository).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(f"Repository path is not a directory: {root}")
    target = root / ".agents" / "skills" / "contextforge-graph"
    skill_file = target / "SKILL.md"
    metadata_file = target / "agents" / "openai.yaml"
    if skill_file.exists() and not overwrite:
        raise FileExistsError(
            f"ContextForge graph skill already exists at {skill_file}; "
            "pass --overwrite to refresh it"
        )
    resource = files("contextforge.bundled_skills").joinpath("contextforge-graph")
    skill_text = resource.joinpath("SKILL.md").read_text(encoding="utf-8")
    metadata_text = resource.joinpath("agents", "openai.yaml").read_text(encoding="utf-8")
    metadata_file.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(skill_file, skill_text)
    _atomic_write(metadata_file, metadata_text)
    return target


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
