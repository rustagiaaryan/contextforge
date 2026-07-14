# Security

## Supported versions

Until the first stable release, security fixes target the latest `main` branch.

## Reporting

Please use GitHub's private vulnerability reporting for `rustagiaaryan/contextforge`. Do not disclose exploitable details in a public issue.

## Threat model

Repositories, issue text, source comments, paths, and Git metadata are untrusted. ContextForge parses but never imports or executes indexed repository code. Subprocesses use argument arrays, Git commands are read-only during indexing, SQLite queries are parameterized, and resolved paths must remain beneath the selected repository root.

The dashboard binds to loopback by default and is intended for local inspection. The MCP server exposes read-only retrieval operations plus explicit local indexing. Users should not expose either service directly to an untrusted network.

Generated databases, model caches, environment files, and benchmark artifacts are ignored. Optional providers read credentials from environment variables; credentials must never be placed in configuration, output packages, logs, or commits.

## Known limits

Static parsing cannot make dynamic Python calls authoritative. Evidence packages can contain adversarial source comments, so downstream agents must treat retrieved text as data, not instructions. Resource caps mitigate but cannot eliminate denial-of-service from intentionally pathological repositories.

