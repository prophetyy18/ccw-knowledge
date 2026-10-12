# cc-workflow Adapter for ccw-knowledge

## What this directory is

This directory documents the **integration surface** between
`ccw-knowledge` and `cc-workflow`. It contains no executable code
that mutates `cc-workflow` — it is intentionally a *proposal* plus
self-contained integration snippets the operator (or a future
automation) can apply.

## cc-workflow integration principles

1. **No automatic capture on Skill boundaries.** ccw-knowledge does
   not insert a "save the conversation" hook at any of cc-workflow's
   six phase boundaries. Capture is explicit and operator-driven.
2. **No replacement of cc-workflow's decision authority.** Each phase
   in cc-workflow (Intent, Reconcile, Spec, Architecture, Module
   Design, Implementation) keeps its current author. Knowledge is
   *evidence*, not authority.
3. **One global Knowledge Skill is enough.** A single
   `knowledge-context` Skill can be invoked from any phase. We do
   not ship one Skill per phase.
4. **cc-workflow's `independent-reviewer` continues to own review.**
   Knowledge review (`knowledge-review`) is a separate concern:
   it promotes *Candidate* Markdown documents in the Vault, not
   Intent/Spec/Architecture artifacts. They are different scopes
   and should not be merged.

## Where to integrate in cc-workflow

cc-workflow's Skills live at:

```
<cc-workflow-repo>/.claude/skills/<phase>/SKILL.md
```

The Skills already follow the standard Claude Code `description`
frontmatter format. The recommended integration is **non-invasive**:

- Add a `knowledge-context` Skill (ours) to either the cc-workflow
  repo (project-scope) or the user's `~/.claude/skills/`
  (user-scope, cross-project).
- Optionally extend the cc-workflow `CLAUDE.md` to add a short
  paragraph reminding the agent that `/knowledge-context` exists.

No other changes are required for V1. The agent can invoke the
Skill manually or rely on its `description` to be matched against
the user's request.

## Example: where to mention knowledge in a phase SKILL.md

If the operator wants a phase Skill (say `architecture`) to be
explicit about when to call knowledge, add a small block to that
Skill's existing guidance section:

```markdown
## When to consult ccw-knowledge

Before drafting the architecture for a non-trivial change, invoke
`/knowledge-context` with the design's open questions (e.g. "why
was X rejected last time", "what is the prior pattern for Y").
Use only the Evidence Pack fields; do not let knowledge replace
the architecture's own authority or its reviewers.
```

Keep the addition tiny — one paragraph, three to five lines. Do
not introduce a mandatory new step or a new gate.

## Why we don't ship a fork or PR

- It would duplicate review and maintenance burden across repos.
- The integration is purely additive; cc-workflow works without
  it. Operators who want it can copy the snippet above.
- Plugin-level distribution via Claude Code means the user can
  enable Knowledge skills independently of any cc-workflow
  version.

## Future direction (V2 and beyond)

- Optional `knowledge-context-bootstrap-cc-workflow` Skill that
  asks the operator to attach a project and offer to register
  cc-workflow's `docs/intents/` / `docs/specs/` as searchable
  source material (read-only). No write-back.
- Optional evidence-format interop: cc-workflow's Verified /
  Supported / Unverified tags can be mirrored by knowledge's
  `confidence: high|medium|low`. We do not auto-promote; the
  mapping is documented in `INTEGRATION.md` if you want to apply
  it manually.
