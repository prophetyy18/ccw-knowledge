# INTEGRATION.md

This document captures the concrete seams between `ccw-knowledge` and
`cc-workflow`. It is *descriptive*: it tells you what to read or
where to write if you decide to integrate.

## 1. cc-workflow structures you can read

These files exist in any project that has cc-workflow initialised.
Reading them is allowed; we do not write to them in V1.

| Purpose | Path |
|---|---|
| Workflow definition | `.claude/skills/*/SKILL.md` |
| Cross-layer rules | `.claude/references/cross-layer-coordination.md` |
| Verification standard | `.claude/references/verification.md` |
| Independent reviewer | `.claude/agents/independent-reviewer.md` |
| Intents | `docs/intents/INT-NNN/INTENT.md` |
| Specs | `docs/specs/SPEC-NNN/SPEC.md` |
| Architecture | `docs/architecture/ARCHITECTURE.md` |
| Modules | `docs/modules/MOD-<slug>/DESIGN.md` |

## 2. Shared concerns with cc-workflow

| Concern | cc-workflow | ccw-knowledge |
|---|---|---|
| Research / verification | `intent/SKILL.md` §17 + `references/research.md` (Fact / Source / Verified) | `knowledge-context` Skill — Evidence Pack (matches / supporting_evidence / conflicting_evidence / unknowns) |
| Evidence classification | `spec/SKILL.md` §13 + `fact-verification.md` (Verified / Supported / Unverified) | `frontmatter.confidence` — `high / medium / low` |
| Review | `independent-reviewer` (Subagent) | `knowledge-review` Skill (operator-invoked; status transitions) |
| Audit / health | none specific | `knowledge-audit` Skill + `ccw-knowledge audit` |

The mapping above is **suggestive**, not enforced. Knowledge does not
modify cc-workflow state files.

## 3. The minimum viable integration

The operator runs:

```bash
# one-time, machine-wide
ccw-knowledge init --vault ~/ObsidianVault
ccw-knowledge install-skills --target user

# per project
cd <project>
ccw-knowledge attach .
```

The Knowledge Skills then become auto-invocable in any cc-workflow
session inside that project. The agent decides (or is told by the
operator) when to invoke.

## 4. Status transitions overlap

cc-workflow keeps three Verification States
(`Review Executed`, `Authority Resolved`, `Implementation Verified`).
ccw-knowledge keeps four knowledge lifecycle states
(`candidate`, `reviewed`, `stale`, `superseded`).

These are *parallel* state machines that track different things.
We deliberately do not auto-mirror one into the other.

## 5. If the operator wants bidirectional evidence pointers

A possible extension (not in V1):

- When cc-workflow's Independent Reviewer emits a Verified/SU fact,
  the operator can call `/knowledge-capture` to put that fact in
  the Vault.
- When the Vault contains a Verified (status=reviewed, confidence=high)
  fact relevant to a SPEC, the operator can manually quote it in
  the SPEC. Knowledge never edits SPECs.

This bidirectional mapping is opt-in and operator-driven.
