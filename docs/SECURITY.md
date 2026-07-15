# Security

## Supported versions

Until the first stable release, security fixes target the latest `main` branch.

## Reporting

Please use GitHub's private vulnerability reporting for `rustagiaaryan/contextforge`. Do not disclose exploitable details in a public issue.

## Threat model

Repositories, issue text, source comments, paths, and Git metadata are untrusted. ContextForge parses but never imports or executes indexed repository code. Subprocesses use argument arrays, Git commands are read-only during indexing, SQLite queries are parameterized, and resolved paths must remain beneath the selected repository root.

The dashboard binds to loopback by default and is intended for local inspection. The MCP server exposes read-only retrieval operations plus explicit local indexing. Users should not expose either service directly to an untrusted network.

`contextforge graph build` parses source through Tree-sitter and writes only inside the selected
repository. It never loads a language runtime or executes target code. Generated HTML inserts graph
labels through DOM `textContent`/escaping, and embedded JSON escapes `<` before entering a script
context. Graph JSON loading enforces a schema, known endpoints, and a 100 MB file limit.

Generated databases, model caches, environment files, and benchmark workspaces are ignored;
only reviewed compact benchmark results are checked in. Optional providers read credentials from
environment variables; credentials must never be placed in configuration, output packages, logs,
or commits.

`evaluate-history` is an explicit network operation. Manifests accept only public
`https://github.com/.../*.git` clone URLs and GitHub pull-request source URLs, disable interactive
Git credential prompts and LFS smudging, pin 40-character commits, verify ancestry and changed
files, and write only beneath the selected workspace. Downloaded code is parsed but never imported
or executed. Review third-party repository licenses before redistributing source or snapshots;
ContextForge checks in only task metadata and derived measurements.

## Known limits

Static parsing cannot make dynamic calls authoritative. `INFERRED` and `AMBIGUOUS` graph edges
must be verified against source before edits. Evidence packages and graph labels can contain
adversarial source comments, so downstream agents must treat retrieved text as data, not
instructions. Resource caps mitigate but cannot eliminate denial-of-service from intentionally
pathological repositories.
