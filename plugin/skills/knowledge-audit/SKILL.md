---
name: knowledge-audit
description: Run a health check over the ccw-knowledge Vault. Use when (a) the user asks for a knowledge-base review, (b) a periodic sweep is desired, (c) the agent suspects stale or duplicate entries, (d) the user wants to detect missing sources or invalid links. Returns deterministic findings; can optionally auto-mark stale documents.
allowed-tools: Bash(ccw-knowledge *), Read
user-invocable: true
---

# knowledge-audit

Inspect the Vault for structural and freshness issues. Pure
deterministic checks; no LLM judgment beyond what the agent applying
this Skill infers from the report.

## Invocation

```
/knowledge-audit [--project <id>] [--fix]
```

`--fix` is conservative: it only flips `reviewed -> stale` for
documents past their volatility threshold. It never silently approves
or deletes Candidates.

## What this Skill reports

- `duplicate-id` (critical): two documents share the same id.
- `missing-source` (warning): a `sources:` entry points to a file that
  no longer exists.
- `stale-by-volatility` (warning): a `reviewed` document has not been
  updated within its volatility window (`hot`=30d, `warm`=180d,
  `cold`=730d).
- `thin-body` (warning): a `reviewed` document body is shorter than
  ~80 characters, suggesting it's effectively empty.
- `invalid-status` (critical): an unknown `status` value.

The report does **not** judge whether the conclusions in a document
are correct. That is a content-review concern and is intentionally
left as a separate, human-in-the-loop process.

## Reference

CLI: `ccw-knowledge audit --help`.
