---
name: "opl-flow"
description: "Use when configuring, diagnosing, tuning, updating, or explaining the OPL Flow Codex experience baseline; starting its durable ledger supervisor; routing multi-machine work; or when the user explicitly asks to use OPL Flow."
---

# OPL Flow

OPL Flow is the Codex experience baseline and work-coordination control layer.
It is an optional `OPL Package(kind=workflow_profile)`: its absence must not
block OPL Base, OPL App, plain Codex, another Package, or domain work.

Flow owns the reusable Profile, recommended model policy, experience-baseline
intent, core workflow Skills, Ledger onboarding contract, and generic Fleet
engine. Framework owns install/update/repair and installed projections. App
owns product UI, user choices, and fallback behavior. A private OPL Instance
owns personal Ledger and Fleet state.

Keep ordinary reasoning model-native. Do not bootstrap a planner/executor role
stack or a second development methodology.

## Choose One Action

Infer the action from natural language. Ask only when two actions would produce
materially different mutations.

| Action | Use when | Load |
| --- | --- | --- |
| `doctor` (`$opl-flow doctor`) | Inspect the effective Codex baseline, Profile, package, model, capabilities, Ledger, or Fleet without repairing by default. | `references/codex-baseline.md`, then `references/terminal-readback.md` |
| `setup` (`$opl-flow setup`) | Establish or repair the owner-supported baseline on this machine; optionally initialize an Instance. | `references/setup-update.md`, `references/package-lifecycle.md` |
| `tune` (`$opl-flow tune`) | Improve `AGENTS.md`, model/reasoning defaults, capability selection, or optional enhancements while preserving user ownership. | `references/codex-baseline.md`, `references/app-integration.md` |
| `update` (`$opl-flow update`) | Update Flow and configured components from their owners, migrate known legacy surfaces, and verify effective discovery. | `references/setup-update.md`, `references/package-lifecycle.md` |
| `start` (`$opl-flow start`) | Formally onboard the owner's complete human Ledger: reuse or create its Dashboard and Bead, complete Linear projection, and the hourly `OPL Flow Supervisor`. | `references/start-onboarding.json`, `references/ledger-start.md` |
| `fleet` (`$opl-flow fleet`) | Configure, inspect, admit, select, or dispatch across Instance-backed machines. | Use `$opl-fleet`; load its Skill instead of expanding Fleet here. |

Natural-language examples:

- "检查/修复 Codex 使用基线" -> `doctor` first, then `setup` only when repair is authorized.
- "优化我的 AGENTS.md 和模型设置" -> `tune`.
- "创建 OPL 总账并每小时监督" -> `start`.
- "配置或使用 OPL Fleet" -> `fleet`.

## Shared Invariants

1. Read the installed Package/Framework projection and effective repo-local
   `AGENTS.md` before deciding what is missing. Documentation and prompts are
   not installed truth.
2. Keep three status planes separate:
   - `package_operational`: Flow itself is installed and callable;
   - `experience_baseline`: recommended Skills/Tools are current or degraded;
   - `specialized_capabilities`: optional capabilities are present or absent.
3. A degraded experience baseline offers the owner-supported repair action but
   does not make the Flow Plugin, Profile, Ledger, or core Skills unusable.
4. `architect-and-simplify` is capability-aware: route to it when installed;
   otherwise perform the same architecture judgment model-natively. Never
   block architecture work because the optional enhancement is absent.
5. Preserve user and owner boundaries. The user owns the effective
   `AGENTS.md`, model selection, additional instructions, and optional pack
   choices. Flow never generates a hidden base prompt.
6. Use the Package manifest as the bundled-core Skill authority. Do not keep a
   second handwritten core list in setup logic or an App contract.
7. Use Framework/package actions for normal install, update, repair, rollback,
   and currentness. Repository-local install helpers are development tools.
8. Read terminal state from the actual owner surface. A plan, test, task
   branch, merge packet, Automation, or UI label is not completion.
9. Installation deploys capabilities only. Installation never runs `start` or
   creates a Dashboard, Bead, Linear project, or Automation. Only an explicit
   `$opl-flow start` performs formal onboarding.

## Core Workflow Routing

- Use `$develop-and-deliver` for multi-step software implementation and
  delivery.
- Use `$coordinate-concurrent-tasks` for multiple Codex tasks, repositories,
  worktrees, machines, or canonical integration.
- Use `$recover-codex-tasks` for interrupted, missing, or ambiguous execution
  state.
- Use `$task-mode-gate` only for real release, deployment, migration,
  destructive/public mutation, or validation-to-production transition.
- Use `$opl-fleet` for machine topology, admission, leases, repository
  currentness, and dispatch.

## Action Contracts

### `doctor`

Default to read-only. Report package operational state, experience-baseline
state, specialized capability availability, model policy, Profile status, and
configured Instance/Ledger/Fleet state independently. Do not repair because a
recommended component is missing unless the user asked to fix or set up.

### `setup`

Treat setup as one agentic action, not a list of commands for the user. Use the
current package owner route, preserve existing user Profile content through the
semantic-merge safety protocol, repair the experience baseline from each
component owner, and initialize private state only when requested or clearly
required by the requested workflow. Do not create the Ledger Dashboard,
Supervisor heartbeat, or Linear projection unless this action was explicitly
`start`.

### `tune`

Tune the smallest requested surface. Preserve explicit user overrides. Flow's
recommended default is `gpt-5.6-sol` with `max` reasoning, but App Auto,
available-model discovery, UI persistence, and user selection remain App/Codex
responsibilities. Load `references/app-integration.md` before changing context
or conversation behavior.

### `update`

Update each component through its owner, migrate only source-proven legacy
surfaces, then verify package bytes, Profile, baseline, optional discovery, and
executor callability. Never use wildcard OPL Skills installation; resolve a
named preset to explicit Skill IDs from the OPL Skills catalog. Update does not
run onboarding or create a second supervision loop.

### `start`

Execute the machine contract end to end. `OPL Ledger` means the owner Instance's
complete human Ledger, not the Supervisor and not only OPL source-development
work. The Supervisor display name is exactly `OPL Flow Supervisor`.

Preserve uniqueness, native task and Automation routes, complete narrow-field
Linear coverage, supervisor decision set, Dolt parity, and the no-auto-archive
boundary. One Supervisor and one hourly heartbeat cover one or more registered
Linear projects; adding a project updates that Supervisor instead of creating a
second loop. Current onboarding registers `OPL Ledger` by default.

The local Codex manages every registered issue by default. Treat `codex-ready`
as an optional compatibility hint. `codex-paused` blocks dispatch only: keep
the issue reconciled and keep consuming its authorized user comments. On each
heartbeat, use `mcp__codex_apps__linear_list_comments` and the saved
per-project Linear comment-ID high-watermark. Deliver each new authorized user
comment exactly once to the matching local Codex task using the comment ID as
the idempotency key. Advance the cursor only after successful delivery or a
documented non-user ignore. Ignore Supervisor, Agent, Automation, and other
non-user comments to prevent feedback loops. Process comments no later than the
next heartbeat. A Codex Cloud delegate conflicts with this route and fails
closed.

Register Ambient Ops in the Ledger as an OPL Fleet observability extension;
it does not create another Supervisor. Validate the final receipt:

```bash
python3 skills/opl-flow/scripts/validate_start_onboarding.py --receipt <path>
```

### `fleet`

Delegate to `$opl-fleet`. The public engine consumes an explicit private
Instance root; it never owns topology, credentials, personal policy, or node
runtime state.

## Finish

Load `references/terminal-readback.md` for every mutation. State which of the
three status planes is current, degraded, unavailable, or not configured, and
name any remaining external authorization or new-session discovery requirement.
Never archive a Codex task without fresh user approval.
