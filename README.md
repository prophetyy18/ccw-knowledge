# ccw-knowledge

> Knowledge Layer for AI Coding Agents. Markdown-first, Obsidian-compatible, plugin-friendly.

`ccw-knowledge` is a long-term knowledge management system designed to
sit alongside (not replace) your development workflow. It pairs a
local, Obsidian-friendly Markdown Vault with a Python CLI and a
Claude Code plugin that exposes five Skills:

- `knowledge-context` — read-only retrieval (default: auto-invocable)
- `knowledge-capture` — save a Candidate
- `knowledge-review` — promote / reject / defer
- `knowledge-audit` — health checks
- `knowledge-bootstrap` — explicit initial extraction

The project is **infrastructure** for an Agent, not another
development controller. It does not own Intent, Spec, Architecture,
Implementation, or Review authority. See `ARCHITECTURE.md` for the
explicit boundary declaration and `adapters/cc-workflow/` for the
integration design with [cc-workflow](https://github.com/prophetyy18/cc-workflow).

## Why this exists

Code-generation agents often:

- Re-do the same web searches across sessions.
- Fail to remember "why X is the way it is".
- Conclude too quickly from one matching document.
- Conflate new evidence with verified knowledge.

`ccw-knowledge` does not solve these by making the Agent smarter.
It solves them by giving the Agent a local, structured, queryable
backlog with provenance and lifecycle states. The Agent decides when
to consult it; the engine decides what state changes are allowed.

## What it explicitly is NOT

- It is NOT an Intent system. Use cc-workflow for that.
- It is NOT a search engine with embeddings or vector DBs.
- It is NOT a daemon. There is no background service.
- It is NOT a heavy marketplace plugin. It is a small set of Skills.
- It is NOT Obsidian. Obsidian may render the same files; we do not
  depend on Obsidian being installed.

## Installation

```bash
git clone https://github.com/prophetyy18/ccw-knowledge
cd ccw-knowledge
pip install -e .          # zero Python dependencies
```

Verify:

```bash
ccw-knowledge --version   # => ccw-knowledge 1.0.0
```

## Quick start

### 1. Connect or create a Vault

The Vault is any directory. You can point it at an existing Obsidian
Vault — we add three sub-directories (`shared/sources`,
`shared/candidates`, `shared/knowledge`, plus `projects/`) and never
touch your existing files.

```bash
ccw-knowledge init --vault ~/Documents/ObsidianVault
```

Output:

```
engine initialised.
  vault: /home/you/Documents/ObsidianVault
  shared: /home/you/Documents/ObsidianVault/shared
  projects: /home/you/Documents/ObsidianVault/projects
```

Subsequent `init` calls on the same path are idempotent.

### 2. Install the Knowledge Skills

For every project on this machine, register the Skills globally:

```bash
ccw-knowledge install-skills --target user
# Skills installed to ~/.ccw-knowledge/skills
```

Or per-project:

```bash
cd ~/code/lp2
ccw-knowledge install-skills --target project
# Skills installed to .claude/skills/
```

Or load the entire bundle as a Claude Code plugin:

```bash
claude --plugin-dir /path/to/ccw-knowledge/plugin
```

### 3. Attach a project

```bash
cd ~/code/lp2
ccw-knowledge attach .                # registers project "lp2"
# Optionally add a marked section to CLAUDE.md/AGENTS.md
ccw-knowledge attach . --update-claude-md
```

This writes **only** `.ccw-knowledge.json` to the project root. It
does not scan your code; it does not edit business files; it does
not register you with any other service.

### 4. Use it from Claude Code

```bash
claude
```

Inside a session the Agent can invoke:

```
/knowledge-context "why does X exist" --depth standard
```

The Skill returns a structured Evidence Pack — title, status,
sources, supporting raw material, important unknowns. Use only the
fields you trust; treat `status: candidate` as a hint, not a fact.

### 5. Capture and review

After a non-trivial investigation, save the result as a Candidate:

```
/knowledge-capture --project lp2 \
    --title "Why the auth flow uses two cookies" \
    --text "..." --tags "auth,design"
```

Then review it explicitly:

```
/knowledge-review --project lp2 \
    --candidate <id> --action approve --notes "..."
```

`--audit-only` runs the structural checks without changing anything.

### 6. Bootstrap (opt-in initial extraction)

To pull an initial set of references from a long-lived project:

```bash
ccw-knowledge bootstrap --project lp2 --max-files 200
```

- Always opt-in. Never auto-trigger.
- Only writes Candidates, never publishes.
- Default globs cover `*.md`, `README*`, `ARCHITECTURE*`,
  `docs/**/*.md`. Pass `--scope glob` to override.
- Default excludes: `.git`, `node_modules`, `venv`, `.venv`,
  `dist`, `build`. Pass `--exclude DIR` to add more.

### 7. Detach

```bash
ccw-knowledge detach .          # local config + registration
ccw-knowledge detach . --keep-local-config
```

Detaching does not delete Vault knowledge. The project's space in the
Vault stays where it is.

## CLI Reference

```
ccw-knowledge init --vault PATH [--force-via-config]
ccw-knowledge attach [DIR] [--project-id ID] [--vault PATH]
                       [--scopes "project:{id},shared"]
                       [--update-claude-md]
ccw-knowledge detach [DIR] [--project-id ID]
                       [--keep-local-config]
                       [--keep-claude-md-section]
ccw-knowledge bootstrap --project ID [--scope glob ...]
                        [--max-files 200]
                        [--max-chars 4000]
                        [--exclude DIR ...]
                        [--dry-run]

ccw-knowledge search QUERY
        [--depth quick|standard|deep]
        [--project ID]
        [--scope shared|project:<id>]
        [--budget N]
        [--limit N]
        [--include-sources]
        [--json]

ccw-knowledge capture --project ID
        (--file PATH | --text BODY)
        [--title ...]
        [--sources CSV]
        [--tags CSV]
        [--category ...]
        [--confidence ...]
        [--volatility ...]

ccw-knowledge propose-update --knowledge ID --project ID
                          --file PATH [--reason "..."]

ccw-knowledge review --project ID
        (--candidate ID | --all)
        --action approve|reject|defer
        [--reviewer NAME] [--notes "..."]
        [--audit-only]

ccw-knowledge audit [--project ID] [--fix]

ccw-knowledge status [--project ID]
ccw-knowledge config show|set KEY VALUE
ccw-knowledge install-skills [--target user|project] [--project-dir DIR]
ccw-knowledge uninstall       # by design a no-op; see CLI help
```

## Knowledge lifecycle

```
candidate --approve--> reviewed
candidate --defer----> stale
candidate --reject---> superseded (kept as deprecated-*.md)
reviewed  --audit --fix-> stale (auto, reversible)
```

The CLI does **not** auto-approve. Candidates require explicit
operator action.

## Knowledge Reconcile (Update first, create second)

When `capture` is invoked, the engine:

1. Looks for an existing document with the same id-slug or
   overlapping tags.
2. If one exists, returns a *plan*:
   - `merge` — append evidence into the existing document.
   - `supersede` — mark the old as superseded and write the new
     one with a `supersedes:` pointer.
   - `defer` — manual decision required.
3. Otherwise creates a fresh Candidate.

The CLI suggests; the operator decides.

## What lives where

```
~/.ccw-knowledge/
    config.json                     # global engine config (vault path)
    projects/<id>.json              # one record per attached project
    skills/                         # if --target user install

<vault>/
    shared/
        sources/                    # immutable raw materials
        candidates/                 # awaiting review
        knowledge/                  # approved shared knowledge
    projects/
        <id>/
            sources/
            candidates/
            knowledge/
            review.log.md           # audit trail for review actions

<project>/.ccw-knowledge.json       # small YAML-ish file, <40 lines
```

## Security model

The CLI enforces logical scope:

- Path traversal (`..`) is rejected.
- Bucket paths that escape their prefix are rejected.
- Writes outside the project's scope raise `ScopeError`.

This is **logical** permission, **not** an OS sandbox. Anyone with
raw filesystem access to the Vault can read any document. For real
isolation, rely on filesystem permissions, run Claude Code as a
dedicated user, or store the Vault on a per-machine directory only
that user can read.

Prompts (Skill descriptions) are the weakest layer. They tell the
Agent when to use a Skill; they do not stop an Agent from doing
something else.

## Integration with cc-workflow

See `adapters/cc-workflow/README.md` and `adapters/cc-workflow/INTEGRATION.md`.

The integration is opt-in:

- Install Knowledge Skills globally (per the steps above).
- Optionally add a short paragraph to your cc-workflow CLAUDE.md
  reminding the Agent that `/knowledge-context` is available.
- Knowledge does **not** edit Intent, Spec, Architecture, or Module
  Design files in the consuming project.
- Knowledge does **not** replace `independent-reviewer`. That
  Subagent continues to own verification.

## Testing

```bash
python3 scripts/run_tests.py
# or
python3 scripts/run_tests.py --unit-only
python3 scripts/run_tests.py --e2e-only --verbose
```

Tests cover:

- Frontmatter parser / writer (round-trip)
- Search depths and Evidence Pack shape
- Reconciliation plans
- Review lifecycle (audit-only, defer, approve, reject)
- Audit findings (missing-source, invalid-status, etc.)
- CLI dispatch and idempotency
- Init / attach / detach lifecycle
- Concurrency-safe atomic writes
- bootstrap never auto-publishes
- install-skills for both user and project targets

## What is implemented in V1

- ✅ Standard CLI
- ✅ Init / attach / detach / bootstrap
- ✅ Three retrieval depths + structured Evidence Pack
- ✅ Capture / propose-update / review / audit
- ✅ Knowledge lifecycle states
- ✅ Reconciliation (Update first, create second)
- ✅ 5 Skills delivered as a Claude Code plugin
- ✅ Cross-platform (Windows + Linux), zero Python dependencies

## What is not implemented (deliberate)

- ❌ Embedding / vector search — out of scope for V1.
- ❌ Daemon / background sync — not needed.
- ❌ MCP server — Agents get the CLI directly.
- ❌ Automatic capture of conversations — too risky.
- ❌ Marketplace validation via `claude plugin validate` — the
  plugin is shipped as a `--plugin-dir` bundle so users can audit it
  directly.
- ❌ Direct editing of cc-workflow's repo — integration is opt-in
  by the operator (see `adapters/cc-workflow/README.md`).

## License

MIT. See `LICENSE`.
