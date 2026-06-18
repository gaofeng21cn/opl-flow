---
name: codex-ops-kit
description: "Codex-wide ops guardrails for high-risk workflow events: multi-worktree or subagent lane start, handoff, resume, absorption, merge, delete, or closeout; cross-repo or broad manifest-style edits; RHO retrospection or Codex session-history audits; release, install, realtime, synced, fresh, or currentness claims; generated/runtime/installed config drift; secret/cache freshness checks; long ops phase evidence; and binary-backed package boundary audits. Use before those events. Do not use for ordinary single-file edits, pure explanation, small feature work, or small bugfixes unless one of those risk events is present."
---

# Codex Ops Kit

Codex Ops Kit is the user-level guardrail layer for risky Codex operations. It turns recurring RHO findings into routable checks and scripts while leaving project facts in each repo's own authority surfaces.

## Core Boundary

- Use this skill for ops risk, not general implementation.
- Keep generic Codex workflow baton state under `~/.codex/state/codex-ops-kit/`.
- Use project profiles only to adapt to existing project truth surfaces.
- Do not create a second truth source for MAS, OPL, Tokscale, or repos with existing ledgers, runtime status, owner receipts, read models, or release authority.
- Treat docs, refs, and old reports as historical context until fresh repo/runtime checks confirm current truth.
- Classify RHO-derived changes by authority before editing global files, project files, or this skill.

## Trigger Matrix

Read only the relevant reference file after this entrypoint loads.

| Risk event | Read | First action |
| --- | --- | --- |
| Start, resume, delegate, absorb, merge, delete, or close out a worktree/subagent lane | `references/lane-closeout.md` | Run `scripts/codex_ops_gate.py status --repo .` |
| Broad multi-file, cross-repo, generated config, installed config, or runtime projection change | `references/manifest-drift.md` | Classify source of truth before editing |
| Run RHO or audit Codex session history | `references/rho-retrospection.md` | Use `scripts/rho_wrapper.py` with `--no-apply` default |
| Make release, install, realtime, synced, latest, fresh, or currentness claims | `references/release-currentness.md` | Audit canonical source and fresh evidence |
| Scan broad roots, large JSONL, rollouts, or session history | `references/bounded-forensics.md` | Take a bounded root or stream budget first |
| Record long ops chains, finalize durable artifacts, or inspect binary-backed packages | `references/ops-ledger-artifacts.md` | Create phase/checklist evidence before claiming done |
| Add or update project profile adapters | `references/project_profiles.md` | Point to existing truth surfaces only |

## Non-Triggers

Do not load the detailed references for:

- Pure question answering or explanation.
- Ordinary small feature or bugfix work in a single repo.
- Single-file documentation edits without release/currentness/authority claims.
- Routine test runs or local formatting.
- Domain-specific work already governed by MAS, OPL, MAG, RCA, Office, UI, security, or research skills without an ops risk event above.

## Minimal Commands

Resolve `scripts/...` relative to this skill directory.

```bash
python3 scripts/codex_ops_gate.py status --repo .
python3 scripts/rho_wrapper.py --project . --budget tiny
python3 scripts/release_url_audit.py --repo .
```

Use scripts as the stable execution surface. Read script source only when changing a script, debugging a script, or needing exact behavior beyond the reference file.

## RHO Absorption

RHO is a discovery engine. Keep RHO runs `--no-apply` unless the winner has been manually classified as one of:

- global Codex rule,
- user-level skill or helper,
- project profile adapter,
- project-owned fact/status/contract update,
- reject.

Promote only task-agnostic guardrails, stable commands, and reusable scripts to this skill. Project facts stay in the owning project.
