# Retrieval Protocol (for `knowledge-context`)

The Skill is a thin wrapper around the `ccw-knowledge search` CLI.
Both Claude (auto-invoke) and the operator (slash invocation) should
follow the same selection rules.

## Determine scope

The Skill first asks the local engine for the project's scope:

```bash
ccw-knowledge status --project <id> --json
```

The `--project <id>` is optional in current versions; if omitted the
engine returns the union of all projects in the Vault. The result lists
the `scopes` that the current session can read.

## Picking arguments for `search`

| Situation | Depth | Budget | Notes |
|---|---|---|---|
| Quick lookup ("is there a note about X?") | quick | 800 | expect 0–3 matches |
| Normal technical investigation | standard | 2000 | default |
| Architecture / Spec decision | deep | 4000 | use only when evidence quality matters more than latency |
| Cross-module change risk | standard | 2500 | look for `category: reference` AND `tags: ...risk...` |
| Stale-data verification | standard | 1500 | add `--include-sources` to see raw material |

If you do not know the project id, omit `--project`. If the user has
not run `init`, the CLI exits with `NotInitialized`. Surface that as
"knowledge base is not initialised; ask the user to run
`ccw-knowledge init --vault PATH`".

## Reading the result

The default (`--text`) output is designed to be pasted into a chat
context. It includes:

- The match headlines.
- The matched-document excerpts.
- A list of supporting raw sources (paths only).
- A list of important unknowns (if any).

The `--json` output is designed for automated processing by other
Skills. Use it when piping into another tool.

## Anti-patterns

- Do not auto-promote a Candidate by side effect.
- Do not write to Vault files from this Skill (this Skill is read-only).
- Do not request `deep` for every question — that's expensive.
- Do not invent matches; the Skill will return zero hits if no
  documents match. That is itself useful information.

## Errors

`ccw-knowledge search` exits with code 2 when the engine is not
initialised. If that happens, tell the user how to fix it and stop
trying to use knowledge for this session.
