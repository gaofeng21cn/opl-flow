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
| Obsidian + Bases | Complete human archive and task navigation | Execution ownership or scheduling |
| Linear | Active-goal projection and authorized human intent | Full history, execution truth, scheduling |
| GitHub and artifact owners | Canonical source, recoverable checkpoints, CI and release evidence | Fleet capacity or Ledger execution ownership |
| Private OPL Instance | Private Ledger, topology, policy, Operations Registry and personal Skills | Public engine code or platform live state |

Flow is one optional Package. Core usage works without a private Instance,
Ledger, Linear, or Fleet. The three discoverable Skills independently route
Flow product operations, software development, and Codex task management.
Ordinary reasoning does not need a method loaded in advance.

## Router, Worker, Fleet, And Ledger

The routers are the attention boundary for the workflow. A selected Router
hands each request to the responsible owner instead of asking every component
to interpret the same event. The Worker performs one bounded execution slice;
it may run in the current task or through a Fleet adapter and may be replaced
without changing the objective. Fleet supplies node/workspace continuity and
protected capacity. The Ledger remains the only durable task truth.

```text
event -> Router -> Ledger owner/next slice -> Fleet capacity -> Worker
      -> checkpoint/result/blocker -> Ledger readback
```

This is an operating principle, not a claim that every handoff is already
automated. Add a mechanism only when a real workflow exposes a missing handoff,
recovery boundary, or capacity decision. Do not create a second task database,
copy a conversation between nodes, or turn the global Supervisor into a
resident execution loop.

Public product code lives in `gaofeng21cn/opl-flow`. Independent
non-development workflows live in `gaofeng21cn/opl-skills`. Each owner keeps
private configuration in its own `opl-instance-<owner>`; private repository
topology is not a public registry.

## Ledger And Human Projection

The Ledger covers the owner's complete work inventory, including non-software
responsibilities. Beads owns the durable graph and lifecycle; a Codex task is
an execution handle that can be replaced without replacing the objective.

Obsidian + Bases stores the complete human task archive: motivation, verified
outcomes, remaining work, owners, source links, and historical records. Bases
indexes those notes; it is not a second task database or execution controller.
Beads/Dolt remains execution truth. Each independently deliverable or decidable
goal has one durable identity; sessions, retries, fixes, and versions are
evidence or progress within that goal, not automatic new cards.

When Linear is enabled, only goals selected for current progression, decision,
or acceptance require one mapped issue. Frozen responsibilities remain visible
without dispatch; completed history and idle workbench roots need no permanent
Linear card. Missing historical cards are not coverage errors and must not be
recreated. Linear owns human intent, priority, due, pause, and cancel input.
The official Linear Connector performs reconciliation; `bd linear sync` is not
this route. Credentials, private paths, logs, full notes, internal metadata,
and checkpoints do not enter the Linear projection.

The [human archive contract](../skills/opl-flow/references/ledger-human-archive.md)
owns archive readback, non-destructive synchronization, goal granularity, and
quota reporting. Saving elsewhere or removing a project association does not
prove platform archival or quota recovery. Historical-copy deletion is a
separate explicitly authorized action after preservation checks.

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

## Implemented Module Boundaries

The three Skill routers select the method and current owner. They compose
Ledger, Worker and Fleet operations; the Ledger does not dispatch work.

- `scripts/opl_ledger.py` owns Beads/Dolt storage operations, initialization,
  permissions, synchronization and metadata write/readback. Workflow and Fleet
  workspace commands delegate through this adapter; Fleet never implements a
  second Beads writer.
- `scripts/opl_execution.py` owns carrier-neutral handoff/result validation and
  admission evidence. It performs no I/O. `opl_task_owner.py` consumes those
  neutral records; the Workflow entry translates existing Fleet receipts through
  `fleet_execution.py` before calling the owner transitions.
- Fleet configuration and Git primitives live in `fleet_control.py`, below
  reconciliation and Profile delivery. These modules have no reverse import.
- Worktree custody records identify the local custodian, executor, task reference
  and cleanup state. They never assign the Ledger execution owner or declare a
  task complete. Version 1 records are read into the explicit version 2 custody
  representation; the next normal write saves only version 2. Existing CLI
  arguments remain aliases for the custody fields.

The physical owners remain unchanged: Beads/Dolt in the private Instance,
Fleet node configuration and state in the existing per-user directories,
Codex-owned sessions, and owner-managed project artifacts. Fleet's existing
Instance pointer binds the local node namespace to one Instance. An explicit
`--instance` cannot silently reuse another Instance's node state; another local
Instance needs a separate OS user or a deliberate node migration.

### Worker Handoff And Return

A handoff contains `attempt_id`, `objective_id`, `owner_id`, `scope`, input and
checkpoint references, and `expected_result`. It refers to owner-managed data;
raw conversations and credentials stay with their owners. A result binds the
same handoff and reports `checkpoint`, `completed`, `blocked` or `unknown`,
artifact/checkpoint references, remaining work and the next action. `completed`
means this execution slice returned evidence; the current Ledger owner still
accepts the objective result.

```bash
python3 scripts/opl_workflow.py worker handoff --handoff-json handoff.json
python3 scripts/opl_workflow.py worker result \
  --handoff-json handoff.json --result-json result.json
python3 scripts/opl_fleet.py dispatch acquire --adapter local-codex \
  --owner-task <objective-id> --handoff-json @handoff.json
```

Managed dispatch accepts the same `--handoff-json`. The lease stores only the
attempt/objective/owner binding and handoff digest. SSH execution must present
that exact handoff; changing scope after admission fails before transport. A
native Codex Worker receives the handoff through its native task tools and
returns the same result structure. Existing capacity-only CLI calls remain
available without introducing task state into Fleet.
