# Contributing to ContextForge

ContextForge welcomes focused issues and pull requests. Install the development environment with `uv sync --extra dev`, create a topic branch, and run the full local gate before submitting changes:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
```

Public interfaces should be typed and documented. New retrieval behavior should preserve provenance, have deterministic tests, and include an evaluation case when practical. Never add repositories, generated indexes, model caches, credentials, or benchmark claims that cannot be reproduced.

Report security issues using the private process in [docs/SECURITY.md](docs/SECURITY.md), not a public issue.

