---
name: "opl-flow"
description: "Use for OPL Flow setup, diagnosis, tuning, update, package release, Ledger onboarding or supervision, Fleet routing, or an explicit request to use OPL Flow."
---

# OPL Flow

OPL Flow is the Codex experience baseline and work-coordination control layer.
It is an optional `OPL Package(kind=workflow_profile)`: its absence must not
block OPL Base, OPL App, plain Codex, another Package, or domain work.

Flow owns the reusable Profile, recommended model policy, experience-baseline
intent, core workflow Skills, Ledger onboarding route, and generic Fleet
engine. Framework owns install/update/repair and installed projections. App
owns product UI, user choices, and fallback behavior. A private OPL Instance
owns personal Ledger and Fleet state.

Keep ordinary reasoning model-native. Do not bootstrap a planner/executor role
stack or a second development methodology.

Flow's task boundary policy uses a four-question Stop Ladder before expanding
scope: user request, necessity, reachable evidence, and current acceptance.
Review/answer/monitor are read-only; change covers the requested result and
necessary consequences. New dependencies, hashing, compatibility layers,
migration frameworks, abstractions, subagents, and repeat audits require a
current reason. The optional `stop-that-shit` Guard may enforce some of these
facts on supported Hook events, but its absence is non-blocking and it is not a
second Flow owner.

## Choose One Action

Infer the action from natural language. Ask only when two actions would produce
materially different mutations.

Load only the references named by the selected action. Do not preload every
Ledger, Fleet, package, and App contract into an ordinary baseline task.

| Action | Use when | Load |
| --- | --- | --- |
| `doctor` (`$opl-flow doctor`) | Inspect the effective Codex baseline, Profile, package, model, capabilities, Ledger, or Fleet without repairing by default. | `references/codex-baseline.md`, then `references/terminal-readback.md` |
| `setup` (`$opl-flow setup`) | Establish or repair the owner-supported baseline on this machine; optionally initialize an Instance. | `references/setup-update.md`, `references/package-lifecycle.md` |
| `tune` (`$opl-flow tune`) | Improve `AGENTS.md`, model/reasoning defaults, capability selection, or optional enhancements while preserving user ownership. | `references/codex-baseline.md`, `references/app-integration.md` |
| `update` (`$opl-flow update`) | Update Flow and configured components from their owners, migrate known legacy surfaces, and verify effective discovery. | `references/setup-update.md`, `references/package-lifecycle.md` |
| `release-package` (`$opl-flow release-package`) | Prepare, publish, and locally activate one first-party OPL Package without rebuilding the release workflow by hand. | `references/package-release.md` |
| `start` (`$opl-flow start`) | Idempotently bind the owner's Ledger Dashboard, Bead, Linear projection, and hourly `OPL Flow Supervisor`. | `references/ledger-start.md` |
| `supervise` (`$opl-flow supervise`) | Run one bounded episode of the existing Ledger Supervisor without duplicating its reusable policy in the Automation prompt. | `references/ledger-supervisor.md`, then `references/terminal-readback.md` |
| `fleet` (`$opl-flow fleet`) | Configure, inspect, admit, select, dispatch, or move a Beads execution owner across Instance-backed machines. | Use `$opl-fleet`; load its Skill instead of expanding Fleet here. |

Natural-language examples:

- "检查/修复 Codex 使用基线" -> `doctor` first, then `setup` only when repair is authorized.
- "优化我的 AGENTS.md 和模型设置" -> `tune`.
- "发布最新 Package 版本" -> `release-package`.
- "创建 OPL 总账并每小时监督" -> `start`.
- An existing Supervisor heartbeat -> `supervise`.
- "配置或使用 OPL Fleet" -> `fleet`.
- "把这个任务换到另一台机器继续" -> `fleet`; migrate the Bead owner, not the chat transcript.

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
4. Route architecture mapping and simplification to the bundled
   `architect-and-simplify` Skill.
5. Preserve user and owner boundaries. The user owns the effective
   `AGENTS.md`, model selection, additional instructions, and optional pack
   choices. Flow never generates a hidden base prompt.
6. Use the Package manifest as the bundled Skill authority for both core owners
   and focused specialists. Do not keep a second handwritten install list in
   setup logic or an App contract.
7. Use the Framework-compiled Flow strategy for normal install, update, repair,
   status, and Full selection. `system_initialize.recommended_skills` is a
   projection of that strategy, not an App catalog. Repository-local install
   helpers are development tools.
8. Read terminal state from the actual owner surface. A plan, test, task
   branch, merge packet, Automation, or UI label is not completion.
9. Installation deploys capabilities only. Installation never runs `start` or
   creates a Dashboard, Bead, Linear project, or Automation. Only an explicit
   `$opl-flow start` performs formal onboarding.
10. For a `change` task, once the deepest verifiable breakpoint and its owner,
    write set, and smallest repair path are known, the first production action
    is an owner-side repair or a traceable `delivery_bridge`. Tests, checks,
    callbacks, and waits are proof or recovery signals, not substitutes for
    repair. After each one returns, if the breakpoint is unchanged choose
    `direct_fix`, `delivery_bridge`, or a real `stop`; if it moved, continue to
    the narrowest `proof`, `acceptance`, or `complete` step. A green test with
    an unmoved breakpoint is not progress, and `ACTIVE` cannot be sustained by
    waiting, monitoring, or adding tests alone.

## Core Workflow Routing

- Use `$develop-and-deliver` for multi-step software implementation and
  delivery.
- Use `$github-ssot-patrol` for scheduled or interactive GitHub CI, open PR,
  and open issue patrols that require SSOT-first intake and deterministic
  closeout.
- Use `$opl-doc` to align developer documentation with live repository truth,
  consolidate competing current narratives, and retire stale documentation.
- Use `$coordinate-concurrent-tasks` for multiple Codex tasks, repositories,
  worktrees, machines, or canonical integration.
- Use `$recover-codex-tasks` for interrupted, missing, or ambiguous execution
  state.
- Use `$codex-app-owner-migration` when a task must continue on another machine
  through a native, user-visible Codex App task. It is the required route for
  App-visible owner migration; SSH/headless CLI is only transport or diagnostic
  support.
- Use `$task-mode-gate` only for real release, deployment, migration,
  destructive/public mutation, or validation-to-production transition.
- Use `$opl-fleet` for machine topology, admission, leases, repository
  currentness, and dispatch.

## Focused Developer Routing

The Package also installs focused specialists adapted from DeepSeek Harness.
They remain narrow entrypoints and do not replace the core owner Skills:

- `$dsh-code-review` and `$dsh-pre-push-checks` specialize the review and
  outgoing-evidence parts of `$develop-and-deliver`.
- `$dsh-archive-agent-notes`, `$dsh-doc-site-sync`, `$dsh-doc-standards`,
  `$dsh-prose-standard`, and `$dsh-trim-cot-leakage` specialize `$opl-doc`.
- `$dsh-translate-docs` is available only on explicit invocation for a
  bilingual documentation pair.
- `$dsh-find-simplifications` routes to the bundled
  `$architect-and-simplify` Skill.
- `$dsh-merging-stacked-prs` requires GitHub's official stack capability; it
  does not emulate a stack with ordinary sequential merges. Framework manages
  its `gh-stack` baseline dependency through the official GitHub CLI extension.
- `$record-browser-gif` records and verifies truthful browser evidence; remote
  asset publication remains a separate authorized action. Framework treats
  `ffmpeg` and `ffprobe` as one paired baseline readiness condition.

These specialists do not introduce DeepSeek Harness Agent Notes, fixed
translation triplets, an archive ledger, or another development methodology.

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

### `release-package`

Load `references/package-release.md` and use its bundled script for the three
thin actions: `prepare`, `publish`, and `activate`. Do not reconstruct inputs or
repeat readbacks manually. Keep owner/tag, Framework projection, public
publication, and local activation as separate authorities. Never commit, tag,
or overwrite the user's Profile from the script. Invoke `publish` only after a
current direct user instruction authorizes the public release; that invocation
records the exact protected-environment approval through GitHub.

### `start`

Load `references/ledger-start.md` and execute its owner-API route. Only an
explicit `start` may create onboarding state. Reuse an exact identity match,
create only when none exists, and fail closed on ambiguity. One active hourly
`OPL Flow Supervisor` covers all registered Linear projects.

Honor `contracts/workflow-policy.json#ledger_supervisor_policy`: preflight the
native owner tools with `list_threads.limit <= 50`, reconcile an unknown dispatch
timeout from the destination task before any bounded retry, and do not advance a
comment cursor until the automated Linear reply has been posted and read back.

Do not synthesize an onboarding receipt or accept local config, a prompt, or a
test as proof. Finish by reading the Dashboard, Bead, heartbeat, Linear comment
cursor, and Dolt parity back from their current owners.

### `supervise`

Load `references/ledger-supervisor.md` and execute one finite episode for the
already configured Dashboard and registered Linear projects. The heartbeat
supplies private identifiers and notification policy; this Skill supplies the
reusable intake, owner, projection, comment-idempotency, dispatch, transport,
and closeout rules. Do not create another heartbeat, keep a monitoring executor
resident, auto-archive a Codex task, or turn the Automation prompt into a
second policy source.

Keep product execution event-driven. The global Supervisor owns Ledger and
macro reconciliation only; each product controller owns its objective graph,
acceptance, blocker repair, and successor dispatch; bounded executors call the
product controller on checkpoint, terminal, or real blocker. Do not poll live
executors on every heartbeat. Use exact thread waits or reads only to recover a
lost executor, a missing callback, or a cross-objective owner/write-set
conflict. A callback wakes the owner but never replaces terminal evidence.

Keep planned finite development in `backlog` until capacity or a declared
dependency releases it. `on_demand` is only for an `interactive_longline` that
the user returns to irregularly and manually; it must never hide a queued
development slice, dependency wait, recovery disposition, or completed
provenance record.

### `fleet`

Delegate to `$opl-fleet`. The public engine consumes an explicit private
Instance root; it never owns topology, credentials, personal policy, or node
runtime state. Cross-machine continuity is a Beads execution-owner migration:
the target may use a newly created Codex task after fresh workspace and node
admission. Native task handoff is optional and never replaces the Ledger claim.

## Finish

Load `references/terminal-readback.md` for every mutation. State which of the
three status planes is current, degraded, unavailable, or not configured, and
name any remaining external authorization or new-session discovery requirement.
Never archive a Codex task without fresh user approval.
