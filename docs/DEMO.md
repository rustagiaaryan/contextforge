# Demo

The final reproducible demo will index a checked-in Python fixture repository, compile evidence for a cross-file routing bug, and open a local dashboard showing routing, anchors, graph expansion, candidate decisions, Git memory, tests, timings, and budget use.

Planned command sequence:

```bash
uv sync --extra dev
uv run contextforge index examples/demo_repo
uv run contextforge compile examples/demo_repo --task-file examples/demo_issue.md --token-budget 4000
uv run contextforge dashboard examples/demo_repo --open
```

This guide will be replaced with verified output and a screenshot once the real engine and dashboard are complete.

