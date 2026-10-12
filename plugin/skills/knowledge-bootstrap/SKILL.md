---
name: knowledge-bootstrap
description: Run an explicit initial knowledge extraction against a project. Produces Candidate documents only (never publishes). Use when the operator decides a project should have an initial set of knowledge references — e.g. after a long-lived project's first encounter with ccw-knowledge. Always opt-in; never auto-trigger.
allowed-tools: Bash(ccw-knowledge *), Read, Glob
user-invocable: true
---

# knowledge-bootstrap

> ⚠️ This Skill has **side effects** and is **not auto-invocable**.

The operator must invoke it explicitly. It writes Candidate
documents under the project's `candidates/` bucket. Each Candidate
starts at `status: candidate`; nothing is auto-promoted.

## Invocation

```
/knowledge-bootstrap --project <id> [--scope <glob>...] [--max-files 200] [--dry-run]
```

- `--scope` accepts multiple globs relative to the project root. If
  omitted, sensible defaults (`*.md`, `README*`, `ARCHITECTURE*`,
  `docs/**/*.md`) are used. Excluded directories: `.git`,
  `node_modules`, `venv`, `.venv`, `dist`, `build`.
- `--max-files` defaults to 200; the Skill will warn and stop
  rather than scan forever.
- `--dry-run` reports what would happen without writing.

## What this Skill does NOT do

- It does NOT copy entire project files into the Vault.
- It does NOT auto-promote Candidates to Reviewed.
- It does NOT modify the project's authoritative documents.
- It does NOT run if the Vault is uninitialised.

## Reference

CLI: `ccw-knowledge bootstrap --help`. See also the reconciliation
rules in the `Knowledge Reconcile` section of the README.
