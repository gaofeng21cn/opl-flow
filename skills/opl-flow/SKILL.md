---
name: opl-flow
description: "Use only for OPL Flow product operations: Profile or capability-baseline diagnosis and changes, Package install, update, repair, or release, Ledger start or supervision, Fleet operation, or an explicit request to use OPL Flow. Excludes ordinary software development and general Codex task management."
---

# OPL Flow

OPL Flow is an optional workflow-profile Package. Flow owns its reusable
Profile, capability intent, Ledger routes, and generic Fleet engine. Framework
owns installation and effective projections; App owns product UI and user
choices; a private OPL Instance owns personal Ledger and Fleet state.

## Coordination model

The three router Skills are the user-facing entrypoints for the OPL workflow.
They select the responsibility that should handle a request; they do not create
parallel task truth or make Fleet a second task controller.

- **Router** manages attention: it identifies the right product, development,
  or native-task responsibility and hands the request to its owner.
- **Worker** carries one bounded execution slice in the current task or through
  a Fleet adapter. A Worker can stop at a checkpoint, result, or blocker and be
  replaced without changing the Ledger objective.
- **Fleet** provides workspace admission, execution continuity, and protected
  capacity when the slice needs another machine or an explicit executor.
- **Ledger** remains the only durable task truth: objective, dependencies,
  current owner, checkpoint, remaining work, and terminal result.

Use the routers as a handoff chain when the request crosses these boundaries:

```text
user intent
  -> selected Router
  -> Ledger owner and next slice
  -> Fleet admission when capacity or continuity is needed
  -> Worker execution
  -> owner result and next Router decision
```

`$software-development` owns implementation and delivery decisions, and hands
off to `$opl-flow fleet` for Fleet admission, workspace continuity, or protected
capacity. `$manage-codex-tasks` owns native task coordination and owner
migration, and uses `$opl-flow fleet` only when the task needs a managed node or
capacity. `$opl-flow` owns the product-level Ledger and Fleet routes. A handoff
keeps the existing owner and write set; it is not permission to start a second
executor.

Choose one product action and load only its named references.

| Action | Use when | Load |
| --- | --- | --- |
| `doctor` | Inspect the effective baseline, Profile, Package, model, capabilities, Ledger, or Fleet. | `references/codex-baseline.md`, then `references/terminal-readback.md` |
| `setup` | Establish or repair the owner-supported baseline on this machine. | `references/setup-update.md`, `references/package-lifecycle.md` |
| `tune` | Audit a model upgrade and tune Profile, Skills, model defaults, or capability selection while preserving user ownership. | `references/codex-baseline.md`, `references/app-integration.md` |
| `update` | Update Flow and configured components through their owners and verify effective discovery. | `references/setup-update.md`, `references/package-lifecycle.md` |
| `release-package` | Prepare, publish, or locally activate one first-party OPL Package. | `references/package-release.md` |
| `start` | Bind the owner's Ledger Dashboard, Bead, Linear projection, and Supervisor. | `references/ledger-start.md` |
| `supervise` | Run one bounded episode of an existing Ledger Supervisor. | `references/ledger-supervisor.md`, then `references/terminal-readback.md` |
| `fleet` | Inspect, admit, select, lease, synchronize, dispatch, or recover Fleet work. | `references/fleet/guide.md` |

Keep package operation, experience baseline, and specialized capability status
separate. Installation deploys capabilities only; it never starts a Ledger.
Read completion from the actual owner surface and load
`references/terminal-readback.md` after every mutation.

Use `$software-development` for software artifacts and
`$manage-codex-tasks` for native Codex task coordination, recovery,
integration, or owner migration. Never archive a Codex task without fresh user
approval.
