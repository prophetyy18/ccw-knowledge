---
name: knowledge-capture
description: Capture a piece of research, an external finding, or a verified bug cause into the local ccw-knowledge Vault as a Candidate. Use when (a) the agent has just verified a previously-unknown fact with a source, (b) a reproducible debugging session revealed a non-obvious cause, (c) the agent found a useful external article / API behaviour that future sessions should remember, (d) a documented design decision captures a rationale the user might forget. This Skill writes a new Candidate document into the project's candidates/ bucket; it does NOT auto-publish.
allowed-tools: Bash(ccw-knowledge *), Read, Write
user-invocable: true
---

# knowledge-capture

Create a Candidate document in the local ccw-knowledge Vault.

> ⚠️ This Skill has **side effects** — it writes a new file to the
> Vault. It is `user-invocable: true` only; it does not auto-run.

## When this Skill is appropriate

The Skill should be considered when the agent has produced verifiable,
reusable knowledge that has **long-term** value beyond the current
turn. Examples:

- A bug's root cause, with a reproducible case and a link to the fix.
- An API behaviour discovered by reading official docs or testing
  against a sandbox.
- A performance number that was actually measured, not estimated.
- A design rationale that explains *why* a particular pattern was
  chosen over an obvious alternative.

The Skill should NOT be used to:

- Save arbitrary opinions without evidence.
- Save an entire chat session (`conversation`-mode is intentionally
  not yet supported in V1).
- Save trivia that only matters to the current ticket.

## Invocation

The Skill accepts a markdown body and a title; the operator decides
whether to use it via the slash command or interactively.

```
/knowledge-capture --project <id> --title "..." --text "..." [--tags t1,t2] [--source URL or PATH]*
```

`*` Only one of `--text` or `--file` is required; both can be supplied
but `--file` takes precedence.

## Lifecycle

Anything this Skill produces has `status: candidate`. It will **not**
be promoted to `reviewed` automatically. A separate review step
(`/knowledge-review`) is required.

## Reconciliation

If an existing knowledge document already covers similar ground, the
Skill surfaces a reconciliation plan via the `Knowledge Reconcile`
protocol (see `ccw-knowledge propose-update`). When this happens, the
Skill may propose an *update* to the existing document rather than
creating a duplicate.

## Reference

The CLI's behaviour is documented in `ccw-knowledge capture --help`.
