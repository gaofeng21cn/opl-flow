---
name: "opl-flow"
description: "Use when a Codex task needs the OPL Flow workflow profile: Direct/Inline/Durable task classification, planner/executor/debugger/verifier routing, risk-based development flow, high-risk Codex ops routing, subagent/worktree lane contracts, durable evidence writeback, or completion-audit/verification-before-completion discipline. Also use when installing or syncing this workflow profile on a new machine."
---

# OPL Flow

OPL Flow is a lightweight Codex-first workflow profile inspired by Trellis and Superpowers, adapted for pragmatic local engineering work. It installs a thin global `AGENTS.md`, role prompts, and the OPL Flow-owned guardrail skills `codex-ops-kit` and `risk-based-development-flow`; detailed debugging and verification execution still routes to external skills such as `systematic-debugging` and `verification-before-completion` when available.

It is compatible with One Person Lab App Full installs. Full installs normally provide Superpowers and common companion skills; OPL Flow should route to the active local Superpowers profile rather than duplicate or replace it. Keep the current local profile unless the user explicitly asks for official full Superpowers.

Use it to choose the smallest reliable path:

- **Direct**: read-only answers, explanations, status checks, or tiny scoped lookups.
- **Inline**: clear implementation, fix, config, or documentation work done in the main Codex session.
- **Durable**: cross-session, cross-repo, release/CI/runtime-authority, or evidence-sensitive work that must write plans, decisions, evidence, or runbooks to files.

Use repo profile sync when the task is to make a development checkout
OPL-native to this workflow layer.

## Core Route

- For repo work, read the target repo's `TASTE.md` when present before using the user-level fallback at `~/.codex/TASTE.md`.
- Treat `TASTE.md` as maintenance preference, not as project fact or machine truth.
- Requirements unclear, solution comparison, task decomposition: use Planner.
- Goal clear and implementation needed: use Executor.
- Bug, test failure, regression, unexpected behavior: use Debugger first.
- Before saying complete/fixed/passing: use Verifier.
- Code, tests, TDD, release/currentness/readiness, or evidence-strength decisions: use `risk-based-development-flow`.
- Worktree/subagent lane start, resume, absorb, merge, delete, closeout, RHO/session-history audit, broad manifest drift, generated/runtime config drift, release/currentness claims, secret/cache freshness, or long ops evidence: use `codex-ops-kit`.
- Long stalls, repeated failures, heartbeat monitors, runtime/currentness/readiness drift, multi-thread stalls, or auto-advance loops: use root-cause-first supervision. Do not stop at surface status; classify the visible symptom, direct failing boundary, cross-surface evidence, owner surface, and repair or decision path.

Do not force heavy process on Direct work. Do not leave Durable work only in chat.

## Root-Cause Supervision

For stalled or monitored workflows, a status check is incomplete until it explains why the state exists and what can change it. The Root-Cause Depth Gate requires:

1. surface symptom: what the user, monitor, runtime, or thread sees;
2. direct boundary: the command, projection, owner route, gate, queue, contract, dependency, or artifact boundary that emitted the symptom;
3. cross-surface evidence: at least one neighboring truth surface that confirms whether the boundary is current or stale;
4. owner surface: the MAS/OPL/project/human/runtime surface that can legally change the state;
5. repair or decision path: code repair, contract repair, owner consumption, human gate, typed blocker, or explicit stop condition.

Produce a blocker-to-owner map with evidence refs, root-cause category, current owner, legal entrypoint, expected artifact or receipt, verification method, and stop condition. Reports that only restate blocked, no live session, queue empty, missing X, or a status label are incomplete and must not close out the audit.

Treat progress as real only when it creates target-facing delta, owner receipt, reviewer/gate delta, route-back, human gate, stable typed blocker supersession, or strict running proof. Queue empty, clean read models, repeated controller actions, focused tests, or repo commits are maintenance evidence unless they unblock the target workflow and fresh readback proves it.

## Completion Audits

When the user asks for "全部落地", "一步到位", "彻底解决", "持续推进直到完成", or similar target-state delivery, Verifier must output **完成度审计** by default.

The audit object must come from the user's latest target, the original plan, a persisted plan/runbook/contract, or lane goals. Do not replace the full plan with the slice that happened to be implemented. For each item, report `done / partial / not_started / blocked`, percent complete, fresh evidence, gaps, and next action.

Only mark `100%` when fresh executable evidence supports the target-state claim. Docs, plans, contracts, refs-only read models, focused tests, or commits do not by themselves prove runtime/readiness/release/owner acceptance.

## Subagent Contract

Default to Codex inline execution. Use subagents only for independent read-only audits, parallel exploration, isolated verification, or clearly separable implementation lanes.

Unless the user explicitly asks for an independent Codex thread / background task, "subagent" means an in-conversation subagent.

If an independent Codex thread is used, the main session must read its result, absorb or discard its diff, remove its worktree, and archive the thread.

Subagent prompt first line:

```text
任务: <one sentence> | cwd: <absolute path> | 权限: read-only/workspace-write | source of truth: <file/command/URL> | 停止条件: <done/blocked/timeout condition>
```

Always include forbidden scope. If writes are allowed, list writable paths or the exact change boundary. Subagents must not spawn more subagents unless the parent explicitly asks.

The main session must verify subagent output before trusting it: inspect diff, evidence, commands, and residual risks.

## Durable Writeback

Route reusable lessons to the right owner. For high-risk Codex ops, first use `codex-ops-kit` and its relevant reference playbook.

- Project/repo long-term rules: nearest-scope `AGENTS.md` or docs/runbook.
- Release, CI, runtime authority, owner-route, currentness decisions: docs/status, docs/decisions, closeout/attempt records, or evidence ledgers.
- Stable commands and tool boundaries: dedicated skill, script README, or project tool docs.
- One-time execution evidence: task, attempt, closeout, journal, or user-requested deliverable.
- User-level Codex workflow: `~/.codex/AGENTS.md`, `~/.codex/prompts/*.md`, or a local skill.

## Installation

For a new machine, clone this repository and run:

```bash
git clone https://github.com/gaofeng21cn/opl-flow.git
cd opl-flow
python3 scripts/install_local_plugin.py
```

That installs the local plugin into `~/plugins/opl-flow`, registers it in the personal marketplace at `~/.agents/plugins/marketplace.json`, and syncs the OPL Flow user profile into:

- `~/.codex/AGENTS.md`
- `~/.codex/TASTE.md`
- `~/.codex/prompts/planner.md`
- `~/.codex/prompts/executor.md`
- `~/.codex/prompts/debugger.md`
- `~/.codex/prompts/verifier.md`

Use `python3 scripts/install_local_plugin.py --no-profile` to install only the plugin without touching user-level Codex prompts.

The install profile includes OPL Flow-native guardrails `risk-based-development-flow` and `codex-ops-kit`. It routes to companion skills such as `systematic-debugging` and `verification-before-completion` when they are available.

When the target machine was installed through OPL App Full, Superpowers normally covers `systematic-debugging`, `verification-before-completion`, `using-git-worktrees`, and `test-driven-development`, and App companion payloads cover common document/tool skills such as `mineru-document-extractor`. OPL Flow should not duplicate or replace those execution surfaces.

For machines that use a local Superpowers profile, `lite` is the quiet default, `expanded` can expose Superpowers v6 planning / SDD / review helpers for long-chain implementation, and `full` should mean the user intentionally enabled the official Superpowers bootstrap.

Ponytail is compatible as an optional simplification lens. If installed, keep its default mode `off` or `lite`, and invoke it explicitly for YAGNI / stdlib-first implementation or over-engineering review. Ponytail must not override `risk-based-development-flow`, `codex-ops-kit`, verifier, fresh-evidence, runtime/currentness/readiness, or completion-audit gates.

Check compatibility:

```bash
python3 scripts/check_companion_skills.py
```

The checker reports `superpowers_profile.profile` as `lite`, `expanded`, `full`, `custom`, or `not_configured` alongside bundle readiness and companion skill coverage.

It also reports optional Ponytail plugin detection and `ponytail.config.default_mode` when configured.

Use strict mode when checking that the bundled OPL Flow guardrails are discoverable:

```bash
python3 scripts/check_companion_skills.py --strict
```

For a complete OPL-family bootstrap that also covers OPL runtime, One Person Lab App, MAS/MAG/RCA/OMA agent surfaces, OPL Doc, and companion tools, follow the One Person Lab guide at `https://github.com/gaofeng21cn/one-person-lab/blob/main/docs/references/current-support/opl-new-machine-codex-bootstrap.md`. BookForge default visibility needs separate OPL/App admission evidence.

OPL Flow does not own OPL runtime or App readiness. Temporal family runtime provider, native helpers, domain module health, GUI shell, App first-run state, and Full readiness belong to One Person Lab App / OPL Framework checks.

## Verification

After installation:

```bash
python3 scripts/install_local_plugin.py --verify-only
```

Then restart Codex so plugin and prompt discovery refresh.

## Repo Profile Sync

Check or sync a repo-local OPL Flow profile:

```bash
python3 <opl-flow-checkout>/scripts/repo_profile.py check --repo-root <repo-root>
python3 <opl-flow-checkout>/scripts/repo_profile.py sync --repo-root <repo-root>
python3 <opl-flow-checkout>/scripts/repo_profile.py sync --repo-root <repo-root> --apply
```

`sync` is dry-run unless `--apply` is passed. Apply mode may update
`contracts/opl-native-profile.json` and OPL Flow managed blocks in `AGENTS.md`
and `TASTE.md`; it must preserve repo-specific guidance outside those managed
blocks and must not edit contracts, source, tests, runtime outputs, or project
truth.
