---
name: knowledge-review
description: Approve, reject, or defer a knowledge Candidate against the ccw-knowledge Vault. Use when (a) the operator has decided a Candidate is ready to publish, (b) a Candidate is clearly redundant and should be deleted, (c) a Candidate needs more evidence before it can be published. Always run structural review first; only the operator can promote a Candidate to a Reviewed document.
allowed-tools: Bash(ccw-knowledge *), Read
user-invocable: true
---

# knowledge-review

Move a Candidate between lifecycle states.

> ⚠️ This Skill has **side effects** and is **not auto-invocable**.
> The operator (or a script the operator trusts) must invoke it
> explicitly.

## Lifecycle

```
candidate --approve--> reviewed
candidate --defer----> stale
candidate --reject---> (moved to knowledge/deprecated-*.md, status=superseded)
reviewed  --flag-old-> stale
```

Rejecting does not delete the document; it moves it under
`knowledge/` with `status=superseded` and a `deprecated-` filename
prefix, so future searches can avoid recommending it.

## Invocation

```
/knowledge-review --project <id> --candidate <id> --action approve|reject|defer [--reviewer NAME] [--notes "..."]
/knowledge-review --project <id> --candidate <id> --audit-only
```

`--audit-only` runs the structural review and prints the report
without changing anything. Use this as a dry-run before approving.

## Structural checks (deterministic)

The CLI runs these automatically before approve:

- Required frontmatter keys (`id`, `title`, `status`).
- Status transitions are legal per `ALLOWED_TRANSITIONS`.
- No duplicate `id` among reviewed and candidate documents.
- Local markdown links resolve.

If any `critical` finding exists, the CLI refuses to approve until
the issue is addressed.

## Authority rule

The CLI does **not** auto-approve. The `--action approve` only works
when an operator has explicitly invoked the command. The Skill
description makes this rule explicit so Claude does not bypass the
review step.

## Reference

CLI: `ccw-knowledge review --help`.
