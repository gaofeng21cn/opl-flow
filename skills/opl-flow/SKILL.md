---
name: "opl-flow"
description: "Use when a Codex task needs the OPL Flow workflow profile: Direct/Inline/Durable task classification, planner/executor/debugger/verifier routing, subagent dispatch contracts, durable evidence writeback, or verification-before-completion discipline. Also use when installing or syncing this workflow profile on a new machine."
---

# OPL Flow

OPL Flow is a lightweight Codex-first workflow profile inspired by Trellis and Superpowers, adapted for pragmatic local engineering work.

Use it to choose the smallest reliable path:

- **Direct**: read-only answers, explanations, status checks, or tiny scoped lookups.
- **Inline**: clear implementation, fix, config, or documentation work done in the main Codex session.
- **Durable**: cross-session, cross-repo, release/CI/runtime-authority, or evidence-sensitive work that must write plans, decisions, evidence, or runbooks to files.

## Core Route

- Requirements unclear, solution comparison, task decomposition: use Planner.
- Goal clear and implementation needed: use Executor.
- Bug, test failure, regression, unexpected behavior: use Debugger first.
- Before saying complete/fixed/passing: use Verifier.

Do not force heavy process on Direct work. Do not leave Durable work only in chat.

## Subagent Contract

Default to Codex inline execution. Use subagents only for independent read-only audits, parallel exploration, isolated verification, or clearly separable implementation lanes.

Subagent prompt first line:

```text
任务: <one sentence> | cwd: <absolute path> | 权限: read-only/workspace-write | source of truth: <file/command/URL> | 停止条件: <done/blocked/timeout condition>
```

Always include forbidden scope. If writes are allowed, list writable paths or the exact change boundary. Subagents must not spawn more subagents unless the parent explicitly asks.

The main session must verify subagent output before trusting it: inspect diff, evidence, commands, and residual risks.

## Durable Writeback

Write reusable lessons to the right owner:

- Project/repo long-term rules: nearest-scope `AGENTS.md` or docs/runbook.
- Release, CI, runtime authority, owner-route, currentness decisions: docs/status, docs/decisions, closeout/attempt records, or evidence ledgers.
- Stable commands and tool boundaries: dedicated skill, script README, or project tool docs.
- One-time execution evidence: task, attempt, closeout, journal, or user-requested deliverable.
- User-level Codex workflow: `~/.codex/AGENTS.md`, `~/.codex/prompts/*.md`, or a local skill.

## Installation

For a new machine, clone this repository and run:

```bash
python3 scripts/install_local_plugin.py
```

That installs the local plugin into `~/plugins/opl-flow`, registers it in the personal marketplace at `~/.agents/plugins/marketplace.json`, and syncs the OPL Flow user profile into:

- `~/.codex/AGENTS.md`
- `~/.codex/prompts/planner.md`
- `~/.codex/prompts/executor.md`
- `~/.codex/prompts/debugger.md`
- `~/.codex/prompts/verifier.md`

Use `python3 scripts/install_local_plugin.py --no-profile` to install only the plugin without touching user-level Codex prompts.

## Verification

After installation:

```bash
python3 scripts/install_local_plugin.py --verify-only
```

Then restart Codex so plugin and prompt discovery refresh.
