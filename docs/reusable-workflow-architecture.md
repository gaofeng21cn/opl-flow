# OPL Workflow Architecture

This document owns the boundaries between Flow, the Ledger, the private
Instance, and external systems. [Capability governance](capability-governance.md)
owns installation composition; [Fleet architecture](opl-fleet-architecture.md)
owns distributed execution. Operational procedures belong to the
[router references](README.md).

## Authorities

| Authority | Owns | Does not own |
| --- | --- | --- |
| OPL Flow | User Profile and capability intent, reusable methods, Ledger adapter, Git lifecycle, Fleet engine | Domain truth, App state, carrier currentness |
| Codex | Reasoning, task decomposition, native execution and coordination | A substitute durable Ledger |
| OPL Ledger / Beads and Dolt | Objectives, dependency graph, owner, checkpoints, remaining work | Agent wakeups, machine mutation, release acceptance |
| Linear | Complete narrow-field human projection and authorized human intent | Execution truth, task storage, scheduling |
| GitHub and artifact owners | Canonical source, recoverable checkpoints, CI and release evidence | Fleet capacity or Ledger execution ownership |
| Private OPL Instance | Private Ledger, topology, policy, Operations Registry and personal Skills | Public engine code or platform live state |

Flow is one optional Package. Core usage works without a private Instance,
Ledger, Linear, or Fleet. The three discoverable Skills independently route
Flow product operations, software development, and Codex task management.
Ordinary reasoning does not need a method loaded in advance.

Public product code lives in `gaofeng21cn/opl-flow`. Independent
non-development workflows live in `gaofeng21cn/opl-skills`. Each owner keeps
private configuration in its own `opl-instance-<owner>`; private repository
topology is not a public registry.

## Ledger And Human Projection

The Ledger covers the owner's complete work inventory, including non-software
responsibilities. Beads owns the durable graph and lifecycle; a Codex task is
an execution handle that can be replaced without replacing the objective.

When Linear is enabled, every user-ledger Bead has one issue with preserved
parent/child hierarchy. Linear owns human intent, priority, due, pause, and
cancel input. Beads owns execution state, blocker, and result. The official
Linear Connector performs reconciliation; `bd linear sync` is not this route.
Credentials, private paths, logs, full notes, internal metadata, and checkpoints
do not enter the projection.

One `OPL Flow Supervisor` serves all registered projects. The native Automation
wakes a bounded episode; Beads does not wake or dispatch Agents. The Dashboard
and Automation are views and execution entry points, never another task
database. Onboarding uniqueness and acceptance belong to
[Ledger start](../skills/opl-flow/references/ledger-start.md); incremental intake,
comment idempotency, state mapping, pause semantics, backoff, and bounded
execution belong to
[Ledger Supervisor](../skills/opl-flow/references/ledger-supervisor.md).

A durable responsibility does not require an idle executor. Finite episodes
release their execution handle after owner result readback; future due dates
and explicit triggers stay on the Bead. Interactive workbenches retain their
user-owned lifecycle. Their exact classification and state mapping remain in
the Ledger references above.

## Private State

| Instance surface | Responsibility |
| --- | --- |
| Ledger | Objectives and execution metadata through Beads/Dolt |
| Repository Governance | Approved repositories, visibility, CI tier, branches and review policy |
| Operations Registry | Service and provider pointers, owners, domains, renewal dates, runbooks and explicit review declarations |
| Fleet | Approved nodes, workspace profiles, topology, capacity policy and sanitized receipts |
| Profile and personal Skills | Private preferences and workflows |

Runtime credentials, SSH routes, lease secrets, databases, sessions, logs,
caches, and exhaustive machine state belong to the OS credential owner or
restricted local configuration/state roots. Do not commit them or copy them
between nodes. Each service repository owns its deployable configuration and
runbooks; the external platform owns its live state.

Operations entries are registry-only unless
`maintenance.next_review_on` explicitly declares a review. Reconciliation
creates a uniquely identified dated Bead only for that declaration. No
declarations means no review tasks or Operations parent. Closing a review
updates the next date in the owning registry; Flow does not invent recurrence.

```text
explicit registry review -> Flow reconciliation -> Beads due/defer
  -> external wakeup -> Codex claim and execution -> owner result
```

## Persistence And Recovery

Initialize Beads only in a clean primary checkout or standalone clone. Linked
worktrees share the Git common-directory Ledger. A clone of an existing Ledger
uses `bd bootstrap --yes`, with `.beads` mode `0700` and checkout-local
`beads.role` set to the user's actual authority.

Embedded Dolt has one writer per machine. Cross-machine mutations use the
official Dolt remote: pull before a coherent mutation, push afterward, then
read back parity. Flow provides safe initialization, Operations reconciliation,
and compact status; ordinary task and Dolt operations remain direct `bd`
commands. Flow does not add another replication protocol.

Workspace currentness and owner transfer are implemented in
`scripts/opl_fleet_parts/fleet_workspace.py` and `scripts/opl_task_owner.py`,
exposed through `scripts/opl_workflow.py`. Fleet's
[architecture](opl-fleet-architecture.md) owns their contract; the
[migration procedure](../skills/manage-codex-tasks/references/migrate-owner.md)
owns native App task preflight and operation ordering. A source implementation
does not prove a particular remote node or completed migration.

## Development And Delivery

Personal workflow optimization starts with the user's effective local Profile.
Only proven reusable behavior is promoted to Flow; the distributed policy never
overrides explicit local preferences. Independent task worktrees preserve
recoverable work, then integrate against current canonical source through
[task coordination](../skills/manage-codex-tasks/references/coordinate.md).

Framework owns Package activation, Profile materialization, capability
projection, and carrier readback. Installation, setup, and repair deploy
capabilities; only explicit `start` creates the Dashboard and Supervisor.
[Machine setup](new-machine-codex-setup.md) owns the user procedure;
[Package release](../skills/opl-flow/references/package-release.md) owns publisher
steps. Source checks, immutable publication, installed carrier state, and
new-executor callability remain separate evidence surfaces.

Each node installs from current component owners and uses compatible versions.
There is no controller-version lockstep or node-to-node payload copier.
Superseded repository names and finished migration phases remain in Git
history; the current architecture has no compatibility identity catalog.
