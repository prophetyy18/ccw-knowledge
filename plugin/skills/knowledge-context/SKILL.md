---
name: knowledge-context
description: Retrieve structured evidence from the local ccw-knowledge Vault. Use when (a) the meaning or rationale behind a variable, name, decision, or constraint is unclear; (b) a change could affect multiple modules and you need to check existing notes first; (c) prior research conclusions, citations, or known limits are needed; (d) two attempts at solving a problem have already failed; (e) sources are in conflict; (f) a high-impact, hard-to-reverse technical decision is being prepared. Do NOT use for routine local edits; do NOT use to replace user Intent, Spec, Architecture, or Implementation authority.
allowed-tools: Bash(ccw-knowledge *), Read, Grep, Glob
---

# knowledge-context

Read-only retrieval against the user's local ccw-knowledge Vault.

This Skill is **auto-invocable**. The `description` above controls when
Claude invokes it. If you (the human) want to force retrieval regardless,
use the slash command `/knowledge-context <query>`.

## When this Skill MUST run

The Skill should run — even if briefly — if the user request matches at
least one of:

- A variable / function / module name whose purpose is unclear.
- A design decision that "feels" arbitrary and might have a recorded
  reason.
- A change that crosses module boundaries.
- Repeated failed attempts at the same task.
- A question about prior research, known limits, or "why was it done
  this way".
- A high-impact decision (data deletion, schema migration, public
  contract change) where a wrong call is hard to reverse.

The Skill should NOT run when the request is a clear local edit:

- "rename this function"
- "fix this typo"
- "add this import"
- "format this file"

## What this Skill does

1. Determine the project's knowledge scope.
2. Run a structured search against the local Vault at the requested
   depth.
3. Return an Evidence Pack (machine-readable by default; `--text` for a
   human-readable rendering).
4. List its own search limits so the caller knows what was *not* covered.

## What this Skill does NOT do

- It does NOT modify the project, the Vault, or any code.
- It does NOT replace cc-workflow's Spec / Architecture / Implementation.
- It does NOT run expensive research or scraping tasks.
- It does NOT assume the user wants every document scanned.

## Invocation

```
/knowledge-context <query> [--depth quick|standard|deep] [--budget N] [--json]
```

When invoked automatically by Claude, the same arguments are used with
sensible defaults (depth=standard, budget=2000 chars).

## How to choose depth

Use the lowest depth that still answers the question.

- `quick` — title / alias / tag matches only; brief summary returned.
  Cheap. Use for "is there anything on file about X?".
- `standard` — reads matched documents and links; cites sources. Use
  for most technical investigations.
- `deep` — wider scope including raw sources and cross-checks. Use for
  high-stakes questions only. Higher cost; explicit budget cap.

## How to handle the result

1. Cite the documents that match. The Evidence Pack returns paths and
   statuses.
2. If a match has `status: stale` or `confidence: low`, treat it as a
   hint, not a fact.
3. If no documents match but raw sources do (`supporting_evidence`
   field is populated), inspect those sources before forming a
   conclusion.
4. If the Skill reports `important unknowns`, you must address them
   before forming a conclusion that depends on the unknown area.

## Boundaries respected

- Knowledge does not edit Intent / Spec / Architecture files.
- Knowledge does not promote Candidates without an explicit
  `ccw-knowledge review --action approve` command issued by an operator.

## References

- `references/retrieval-protocol.md` — how to actually invoke the CLI
  from this Skill; selection of search arguments.
- `references/evidence-format.md` — how to read the Evidence Pack.
