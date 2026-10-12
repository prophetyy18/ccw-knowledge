# Evidence Pack Format (for `knowledge-context`)

The CLI's `--json` output uses the following structure. The agent
should parse these fields carefully and never assume a field that is
absent or `null`.

```json
{
  "query": "the user's question",
  "depth": "quick | standard | deep",
  "scope": ["project:lp2", "shared"],
  "matches": [
    {
      "id": "document-id",
      "title": "Document Title",
      "status": "candidate | reviewed | stale | superseded",
      "confidence": "high | medium | low",
      "category": "concept | topic | reference",
      "scope": "project:lp2",
      "path": "/abs/path/to/doc.md",
      "score": 7,
      "excerpt": "...short excerpt with [matched] markers...",
      "matched_fields": ["title", "tag", "body"],
      "tags": ["..."],
      "sources": ["..."],
      "aliases": ["..."],
      "summary": "first non-heading paragraph"
    }
  ],
  "supporting_evidence": ["paths to raw source files that mention the same tokens"],
  "conflicting_evidence": ["stale markers, conflicting citations"],
  "unknowns": ["important unknowns the Skill could not cover"],
  "search_limits": {
    "budget_used_chars": 1234,
    "scanned_documents": 42,
    "queries_run": 1,
    "depth": "standard",
    "context_budget_chars": 2000
  },
  "truncated": false
}
```

## How to interpret each field

- `status: candidate` — not yet reviewed. Do not treat as authoritative.
- `status: reviewed` — passed structural + authority review. Treat as
  the canonical version unless newer evidence contradicts it.
- `status: stale` — outdated. Re-verify before relying on it.
- `status: superseded` — replaced by another document; check
  `superseded_by` field via `--json` (not present in this layout yet).
- `confidence: high` — multiple sources or direct evidence.
- `confidence: medium` — at least one direct source.
- `confidence: low` — inference; treat as a hypothesis.
- `truncated: true` — context budget was hit; some matches were
  omitted. Try a larger `--budget` or a more specific query.

## Honest reporting rule

The agent must not invent citations. If `matches` is empty but
`supporting_evidence` is non-empty, the agent should report:

> "No knowledge documents matched, but raw sources exist that mention
> the topic. Paths: [...]"

If neither is populated, the answer is "no knowledge on this topic in
the permitted scopes". This is a useful answer on its own.

## Two-card rule (recommended)

When reporting back to the user, prefer two sections:

1. **What is known** — bullet list of relevant matches.
2. **What is uncertain** — explicit list of unknowns, and what you
   did *not* search.

This avoids the "found a matching article = done" trap that produces
short-sighted conclusions.
