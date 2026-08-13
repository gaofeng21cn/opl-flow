# OPL Reusable Development Workflow Architecture

Owner: `OPL Flow`
Purpose: `reusable_workflow_target_and_migration_boundary`
State: `target architecture and migration authority`
Scope: product names, module ownership, repository boundaries, private-instance
boundaries, onboarding, and migration order for the reusable development
workflow.
Machine boundary: This document owns the reusable workflow target, naming, and
repository boundaries. Contracts, source, tests, owner surfaces, and fresh
readback own executable behavior and current machine state.

This document is the SSOT for the reusable workflow system. Package/carrier/
executor composition remains owned by
[Capability governance](./capability-governance.md). Current installed behavior,
repository bytes, and machine state remain proven only by their contracts,
source, owner surfaces, and fresh readback.

## One Product

Users install and understand one product: **OPL Flow**.

OPL Flow is the **Codex experience baseline and work-coordination control
layer**. It keeps Codex model-native:

- Flow owns the concise user Profile, model/reasoning recommendation,
  experience-baseline intent, and progressive primary Skill.
- Codex owns task decomposition, task creation, agent execution, conversation
  coordination, and recovery.
- **OPL Ledger** uses Beads only as the durable task ledger. It does not replace
  Codex scheduling or dispatch agents.
- **OPL Fleet** is the optional Agent-native distributed execution and
  task-continuity control plane. It supplies multi-machine enrollment,
  compatible workspace currentness, admission, protected execution, and
  owner-safe continuation while the Ledger remains task truth.
- Linear is the complete human-readable projection of the user Ledger. Codex
  maintains every Bead through the official Linear Connector with a narrow
  field set; Linear is not the execution or ledger authority.
- Gas City/Gas Town is not part of the supported architecture.

## Product And Repository Names

| Product term | Target physical owner | Role |
| --- | --- | --- |
| **OPL Flow** | `gaofeng21cn/opl-flow` | Single public product, Codex Plugin/Profile, model and experience-baseline policy, six-action router, core workflow Skills, Ledger adapter, Git lifecycle, and Fleet engine |
| **OPL Ledger** | OPL Flow module backed by Beads | Dynamic Program, slice, dependency, owner, task, checkpoint, and remaining state |
| **OPL Fleet** | OPL Flow module | Agent-native distributed execution and task continuity: multi-machine join, compatible workspace currentness, lease/admission, execution adapters, and owner-safe continuation |
| **OPL Skills** | `gaofeng21cn/opl-skills` | Optional, independently installable public enhancements |
| **OPL Instance: `<owner>`** | one private repository per owner; for this owner `gaofeng21cn/opl-instance-gaofeng` | Private Ledger data, Fleet nodes/policy, repository governance, Operations Registry, private overlays, personal Skills, and sanitized receipts |
| **OPL Personal Skills** | `skills/` inside the owner's OPL Instance | Private or personal Skill source; not a separate user-facing product |

The table above is the current repository-identity boundary. Superseded names
remain reserved provenance and are never canonical URLs or source owners. A
physical rename or redirect does not prove authority consolidation: generic
Fleet code, private instance data, contracts, installed routes, and live nodes
move only through their owning migration and readback gates.

The dedicated [OPL Fleet architecture SSOT](./opl-fleet-architecture.md) owns
Fleet's positioning, task model, authority boundaries, design assessment, and
capability roadmap. This document owns how Fleet composes with the rest of OPL
Flow.

The product framing is Slurm-class job control for HPC, Kubernetes-class
container control for cloud workloads, and Agent-native control for durable
Agent identity, state, context boundary, permission, budget, dynamic task graph,
and lifecycle. Existing Agent frameworks and execution engines remain valid
adapters. A control Agent may translate natural-language intent into a
Ledger-owned graph and supervise worker Agents, but deterministic contracts
continue to guard identity, authority, budgets, leases, checkpoints, and
terminal readback.

## Authority Layout

The target public repository stays shallow while the codebase is small:

```text
opl-flow/
|-- .codex-plugin/
|-- profile/
|-- skills/
|   |-- opl-flow/
|   |-- coordinate-concurrent-tasks/
|   |-- codex-app-owner-migration/
|   |-- develop-and-deliver/
|   |-- github-ssot-patrol/
|   |-- opl-doc/
|   |-- opl-fleet/
|   |-- task-mode-gate/
|   `-- recover-codex-tasks/
|-- scripts/
|   |-- opl_workflow.py        # small workflow and Ledger entry
|   `-- opl_fleet.py           # generic Instance-backed Fleet engine
|-- contracts/
|-- docs/
`-- tests/
```

Keep Ledger and the Fleet engine inside OPL Flow. Do not split them
into packages or internal module trees until independent consumers prove that
need.

## Primary Entry And Status Planes

`$opl-flow` is a progressive router, not a monolithic prompt. It exposes six
stable actions and loads only the references required by the selected action:

| Action | Responsibility |
| --- | --- |
| `doctor` | Read-only diagnosis of package, Profile, model, baseline, optional capabilities, Ledger, and Fleet |
| `setup` | Establish or repair the owner-supported Codex baseline and optional private state |
| `tune` | Optimize `AGENTS.md`, model/reasoning settings, or capability selection without overriding the user |
| `update` | Update through component owners, perform source-aware migration, and verify effective discovery |
| `start` | Idempotently create or reuse the Dashboard, Bead, complete Linear projection, and hourly supervisor |
| `fleet` | Route node admission, currentness, leases, selection, and dispatch to `$opl-fleet` |

Framework and App report three independent planes:

1. `package_operational`: Flow installed, enabled, and callable;
2. `experience_baseline`: recommended research, Office, and extraction
   capabilities, where missing means `degraded` with a repair action;
3. `specialized_capabilities`: optional capabilities such as
   `architect-and-simplify`, where absence is normal.

Only the first plane controls Flow callability. App consumes the generic
Framework projection and never parses Flow policy or keeps a companion list.
Flow recommends `gpt-5.6-sol + max`; App owns Auto resolution, UI persistence,
explicit user selection, and fallback. `opl_flow_context` is installed-state
metadata only, never a hidden prompt, and is omitted when Flow is absent.

The supported interaction path is:

```text
Linear human intent <-> local Codex/OPL Flow <-> Beads Ledger -> Linear complete narrow-field projection
                                      |
                                      +-> GitHub delivery evidence
                                                        |
                                                      Fleet
```

Codex maintains exactly one Linear issue per user-ledger Bead and preserves the
Bead hierarchy. Linear owns human intent, priority, due, pause, and cancel
fields; Beads owns execution state, blocker, and result. GitHub remains
the branch/PR/CI/release evidence authority. Credentials, local paths, logs,
full notes, internal metadata, and checkpoints never enter the Linear
projection. The official Linear Connector, not `bd linear sync`, owns this
onboarding and routine reconciliation route.

Each user gets one private instance:

```text
opl-instance-<owner>/
|-- .beads/                    # durable dynamic task ledger
|-- fleet/                     # nodes, policy, assets, sanitized receipts
|-- governance/                # durable repository/account policy
|-- operations/                # services, providers, domains, renewal metadata
|-- profile/                   # private overlays
`-- skills/                    # OPL Personal Skills
```

Never commit credentials, tokens, SSH routes, lease nonces, local absolute
paths, sessions, histories, logs, caches, runtime databases, or exhaustive
machine state. Those remain in the OS credential owner, `~/.config/opl-flow/`,
or `~/.local/state/opl-flow/` with restrictive permissions.

## Ledger And Governance

The private instance contains related but distinct authorities:

| Authority | Change rate | Owns | Does not own |
| --- | --- | --- | --- |
| OPL Ledger / Beads | frequent | objectives, slices, dependencies, task/thread references, checkpoints, remaining work | repository policy, machine mutation, agent dispatch |
| Repository Governance | infrequent | active repositories, visibility, CI tier, default branch, review triggers | task progress, Fleet execution |
| Operations Registry | periodic | services, deploy owners, provider references, domains, renewal dates, health/runbook pointers, optional review declarations | deployable configuration, credentials, provider live state, task progress |
| OPL Fleet state | periodic | approved nodes, capability policy, sanitized readback | task truth, source code authority, hosted-service inventory |

OPL Fleet may consume Repository Governance to discover approved repositories.
It must not rewrite governance policy as a side effect of synchronization.
Repository policy changes remain explicit owner actions.

### Scheduled Work

Beads stores `due`/`defer`, dependencies, owner, and completion state. An
Operations Registry asset is registry-only by default. OPL Flow reconciles it
into a uniquely identified Bead only when that asset explicitly declares
`maintenance.next_review_on`; a registry with no declarations creates neither
review tasks nor an Operations parent Program. A Codex Automation, cron job, or CI schedule
may wake a new Codex task to run reconciliation and inspect `bd ready`; Beads
itself is not a scheduler or agent dispatcher.

Compared with a recurring single-conversation task:

| Behavior | Single conversation timer | OPL Ledger flow |
| --- | --- | --- |
| Durable task truth | conversation state | Beads/Dolt |
| Wakeup | Codex Automation | Codex Automation |
| Missed wakeup | may lose continuity | next wakeup resumes from Beads |
| Duplicate wakeup | prompt-dependent | deterministic `external_ref` deduplication |
| New conversation/machine | manual context reconstruction | `bd bootstrap` / `bd dolt pull` |

The supported recurring pattern is therefore `explicit review declaration -> Flow
reconcile -> Beads due/defer -> external wakeup -> Codex claim/execute`. Closing
an Operations review includes updating `next_review_on`; the next reconciliation
then creates the next dated occurrence. Flow does not infer a recurrence that
the owning registry did not declare.

Beads locates its database through the Git common directory. First
initialization therefore runs only in a clean primary checkout or standalone
clone; linked task worktrees share that ledger after initialization instead of
creating separate task databases.

Embedded Dolt is single-writer per machine. Multi-machine work uses the
official `refs/dolt/data` remote: `bd dolt pull` before a coherent write batch,
then `bd dolt push`; a new clone uses `bd bootstrap --yes`. These remain direct
owner commands; OPL Flow does not wrap them or add a second replication protocol.
After bootstrap, keep `.beads` at mode `0700` and configure the checkout-local
`beads.role` as `maintainer` or `contributor` according to the user's authority.

Each service repository continues to own Compose files, `netlify.toml`,
deployment scripts, health checks, and rollback procedures. External platforms
such as a NAS, Netlify, a registrar, and a DNS provider own their live state.
The private Operations Registry stores only non-secret owner pointers,
maintenance metadata, expiry dates, and optional review schedules. OPL Ledger turns explicitly due
reviews, renewals, migrations, and incidents into work; Linear may display that
work. Neither Ledger nor the registry copies credentials or becomes a second
deployment control plane.

## Developer Workflow

1. The developer validates personal workflow changes first in the effective
   local `~/.codex/AGENTS.md`.
2. Codex creates and coordinates tasks natively. OPL Ledger persists only the
   durable graph and recovery facts.
3. Git work proceeds in task-owned worktrees. Overlap is an integration risk,
   not a development-time global lock.
4. Owners push recoverable task checkpoints and replay against fresh
   canonical `main` before integration.
5. Only proven reusable behavior is promoted into OPL Flow.
6. After an OPL Flow release, each Fleet node updates from component owners and
   proves installed behavior by fresh readback.

## Development Repository Currentness

Every managed node uses `~/workspace` (or an explicit absolute
`OPL_WORKSPACE`) as its development root. Repository bytes always come from the
repository's official Git remote, never from another Fleet node.

The repository reconciliation invariant is:

1. discover existing first-level Git checkouts with a GitHub remote belonging
   to the configured owner;
2. use the current branch's configured Git upstream as the authority and run
   `git fetch --prune <remote>`; report a missing upstream instead of guessing;
3. update only a clean checkout on its default branch with
   `git merge --ff-only origin/<default>`;
4. never reset, rebase, merge, switch, or delete a dirty checkout, task branch,
   detached checkout, local-ahead branch, or diverged branch;
5. report those states for the owning task to checkpoint or integrate;
6. run at node reconciliation, before development dispatch, and on explicit
   operator request.

This keeps clean canonical checkouts current while preserving independent
multi-machine work. Fleet synchronization cannot replace the task owner's duty
to push checkpoints and integrate against fresh canonical SSOT.

The executable surface is:

```bash
python3 scripts/opl_workflow.py fleet --instance <opl-instance> repos status
python3 scripts/opl_workflow.py fleet --instance <opl-instance> repos sync
```

`opl-fleet` is the stable node-local command installed during enrollment. The
Flow workflow entry remains the public user-facing surface.

`codex-app-owner-migration` is the first-party route for moving a durable task
owner to a native, user-visible Codex App task. It requires the complete
Instance repository allowlist and target App readback; SSH/headless CLI is only
transport support and never a terminal owner substitute.

### Task-Capacity Dispatch

Fleet complements rather than replaces HPC, cloud, container, CI, and workflow
schedulers. Those systems may remain execution adapters. Fleet owns the
Agent-specific continuity around a distributed attempt: durable objective
binding, compatible workspace admission, protected ownership, checkpoint and
unknown-result semantics, and task-level terminal readback.

The first supported Flow/Fleet dispatch contract is deliberately small:

```text
resource requirements -> plan -> fresh doctor -> controller lease
  -> execution adapter -> result readback -> release
```

`dispatch plan` reads the current sanitized asset catalog and active leases to
produce candidates. `dispatch acquire` repeats the admission decision against a
fresh node doctor before taking a controller-authoritative lease. `dispatch
verify` checks the lease identity, owner, requirements, admission receipt,
control commit, and remaining TTL. `dispatch release` performs the owner CAS
against the controller's private 0600 lease store. Dispatch does not create a
second state database.

The Bead may carry one `metadata.opl_execution_requirements` object conforming
to `contracts/execution-requirements.schema.json`. It is task intent, not live
capacity: adapter, required capabilities, host and GPU memory, CUDA or Metal,
optional GPU model, workload class, priority, preemption phase, and TTL. Fleet
binds the admitted values into the lease. GPU nodes remain peers; model and
memory differences affect eligibility or expected duration, not a static node
priority.

The current real adapters are `local-codex` (no Fleet lease), `lease-only`
(capacity reservation for an explicit caller-owned executor), and
`ssh-session` (one structured argv through a private SSH route after lease
verification). Windows SSH routes execute inside WSL. The existing GitHub
Runner start/stop transaction remains the runner adapter boundary but does not
submit a GitHub job. `remote-codex` uses Fleet for sanitized node admission and
lease ownership, then uses the native Codex App connection for task creation or
continuation and terminal result readback. Pairing, prompts, sessions, and task
results remain Codex-owned and are not copied into Flow or the private Instance.
A plan, lease, connected device, or created task is never an execution result.

`ssh-session` does not accept a composed shell string. It returns bounded
stdout/stderr, exit code, and timing directly to the controller without storing
task output in Git, the Instance, or the lease database. Unknown SSH transport
state retains the lease and requires read-only reconciliation before retry.
Known results require an explicit owner release.

### Task Identity And Cross-Machine Continuity

Beads/Dolt is the objective and current execution-owner SSOT. GitHub is the
code-currentness, recoverable-checkpoint, and delivery-evidence authority.
Fleet owns compatible workspace currentness, node admission, protected
capacity, and adapter-bound execution. A Codex task or thread is a replaceable
executor handle; native conversation handoff is an optional shortcut, not the
continuity contract.

Declarative workspace bootstrap/currentness and compare-and-swap owner
migration are active source work. The target private Instance profile declares
node IDs, a workspace root, an environment contract, an explicit repository
allowlist, and Automation placement. Admission fails closed for dirty, ahead,
diverged, detached, task-branch, remote-mismatch, active-worktree, or stale
control states. Missing repositories are staged and cloned from their official
owners; existing repositories use clean fast-forward-only synchronization.

The target owner migration transaction is:

```text
prepare source checkpoint -> target workspace preflight -> atomic target claim
  -> target verification -> source release/completion
```

The claim is the only owner mutation and binds the execution owner, replaceable
thread handle, node, generation, workspace fingerprint, and checkpoint to the
same Ledger objective. After claim, recovery uses a reverse migration rather
than automatic rollback. Every Ledger mutation follows pull, exact read, one
metadata mutation, push, then pull/readback; an unknown push result permits
read-only reconciliation, not another write attempt. Ordinary task migration
does not move Automations. A singleton Supervisor moves only after old-disabled
and new-active owner readbacks prevent dual heartbeat.

This target remains unimplemented from the public user's perspective until the
workspace and owner-migration contracts, source, tests, canonical integration,
and real cross-machine readback have landed.

This keeps Codex's native task and agent coordination in charge. Flow routes a
task with declared resource needs; Fleet admits capacity; the selected
executor reports the actual work result. The hourly supervisor may inspect and
continue such work, but it is not a hidden general-purpose job scheduler.

Dynamic composition has two separate meanings. OPL Flow installs one stable
primary Skill plus bundled specialist Skills; Codex loads the specialist
instructions only when task semantics route to them. Separately installed OPL
Skills remain optional enhancements. The private Instance and Fleet runtime are
consulted only for tasks with explicit remote resource requirements. Thus OPL
Flow is the common operating layer without making every optional capability or
machine backend a permanent context dependency.

## Public Onboarding

The public entry remains the Codex-native carrier:

```bash
codex plugin marketplace add gaofeng21cn/opl-flow
codex plugin add opl-flow@opl-flow-local
```

The primary first-session actions are:

```text
Use $opl-flow doctor to inspect my effective Codex baseline.
Use $opl-flow setup to establish or repair that baseline.
Use $opl-flow start to create or reuse my OPL ledger Dashboard and supervise it every hour.
```

The resulting heartbeat calls `$opl-flow supervise` for one bounded episode.
Its prompt retains private inputs and scheduling only; reusable intake,
projection, comment, owner, and terminal rules live in
`skills/opl-flow/references/ledger-supervisor.md`. The read-only
`ledger supervisor-snapshot` command produces the compact dynamic Beads/Dolt/Git
input and fails closed on malformed execution metadata or duplicate Linear
mappings.

The hourly episode is incremental by default. One `list_threads` inventory and
batched zero-wait `wait_threads` cursors select changed live tasks; Linear issue
`updatedAt` waterlines select which issues may need comment intake. Only new,
changed, due, or ambiguous objects expand to exact task and owner reads.
`next_review_at` supplies external-review backoff, while missing cursors,
policy/schema changes, unknown timeouts, explicit owner requests, and the
lower-cadence 24-hour audit restore complete coverage. Observation cursors live
in the private Supervisor memory location, not in a second public task store.

`start` discovers the saved project and unique private Instance, then uses Codex
native task and Automation tools plus official `bd` and `opl_workflow.py` routes.
It reuses or creates exactly one local Dashboard task, one Bead bound by
`codex://thread/<thread_id>`, and one hourly supervisor Heartbeat. Every run
ends with thread, Bead, Automation, Linear full-coverage narrow-field parity,
and Dolt parity readback. Ambiguous matches fail closed; Automation, Linear,
and the Dashboard never replace Beads/Dolt as the internal task ledger.

The `$opl-flow` Skill coordinates these steps:

1. doctor Codex, Git, GitHub authentication, and Beads;
2. distinguish package failure, degraded baseline, and optional absence;
3. install or repair missing baseline capabilities only through owner-supported channels;
4. create or connect one private OPL Instance only when durable state is requested;
5. initialize Beads without overwriting `AGENTS.md` or Git hooks;
6. back up and safely merge the OPL Flow Profile;
7. optionally connect Linear or enroll Fleet nodes through outbound authentication;
8. finish with live readback of all applicable status planes.

The orchestration stays model-native rather than reimplementing package managers
or owner APIs. `scripts/opl_workflow.py status` is the machine-readable doctor;
Framework owns Profile materialization and safety; ordinary Dolt operations
remain direct `bd` calls, while Linear projection uses the official Linear
Connector and never requires `bd linear sync`; Fleet remains optional. Only external private
repository creation, OAuth, or another owner-required authorization remains
interactive. Core setup does not require OPL App, a continuously running
controller, inbound SSH, Linear, or Fleet.

## Migration

### Phase 0: Architecture And Facade

- Publish this SSOT and brand vocabulary.
- Add the safe repository-currentness surface to the existing Fleet engine.
- Keep all current repository URLs and runtime owners valid.

### Phase 1: Unified OPL Flow Entry

- **Implemented in source:** safe Beads initialization, Operations Registry
  reconciliation, and the Instance-backed Fleet entry. Ordinary ledger and
  Dolt operations use the official `bd` CLI directly; Codex maintains complete
  narrow-field Linear coverage through the official Linear Connector.
- **Implemented in source:** the guided `$opl-flow setup` / `update` Agent
  workflow plus machine-readable tool/auth/Profile/Ledger/Fleet readback. The
  source script remains a narrow owner surface, not a second package manager.
- **Implemented in 0.1.30 source:** `$opl-flow start`, its machine-readable
  uniqueness/supervision contract, and receipt validation for one Dashboard,
  one Bead, one hourly Heartbeat, complete Linear projection parity, and final
  Dolt parity.
- **Implemented in 0.1.30 source:** the progressive `doctor/setup/tune/update/
  start/fleet` router, workflow policy v4 with three status planes, the sixth
  bundled `opl-fleet` Skill, and capability-aware optional architecture routing.
- **Pilot:** initialize one private Instance ledger and use one Operations
  Program before making Ledger a default onboarding dependency.
- **Implemented in source:** a two-level qualification planner and receipt
  validator. Routine releases bind one candidate's immutable identity and use
  one reference platform for fresh plus upgrade. The full
  macOS/Linux/Windows-WSL matrix, Core without Linear/Fleet, and real
  new-session Skill invocation are reserved for first certification, boundary
  changes, incidents, or explicit recertification. This evidence binding does
  not add a shared version cohort; owner install, publication, and live
  platform receipts remain external terminal evidence.

### Phase 2: Authority Consolidation

- **Implemented in source:** the generic Fleet engine is owned by OPL Flow and
  consumes an explicit private Instance root; personal node policy, assets, and
  the receipt workflow live under `opl-instance-<owner>/fleet/`.
- **Compatibility rollout:** existing personal nodes may continue invoking the
  `codex-fleet` command while it delegates to the Flow engine. The alias is not
  a source or data authority and can be retired after installed readback.
- Move reusable `codex-machine-sync` behavior into OPL Flow after the Fleet
  engine rollout; keep its private preset in the Instance.
- Move workflow-coupled Skills into OPL Flow.
- Move Fleet private data, Repository Governance, the Operations Registry,
  private overlays, personal Skills, and Beads data into
  `OPL Instance: Gaofeng`.
- Keep OPL Skills only for optional, independently useful public enhancements.
- Maintain exactly one active source owner for every Skill and contract during
  transfer.

### Phase 3: Repository Identity Boundary

- The canonical public and private repository identities are the owners listed
  in the Product And Repository Names table. Source constants, schemas,
  validators, presets, installer routes, Git remotes, raw/API URLs, workflows,
  `skill-reference`, and managed node routes must point directly to them.
- Superseded identities may appear only as historical provenance or explicit
  owner-scoped migration inputs. They are not active sources, aliases, fallback
  routes, or authority, and machine-readable contracts must not depend on a
  redirect.
- Repository Governance remains the sole owner for physical GitHub rename,
  redirect, topics, settings, Actions, and remote readback. OPL Flow owns only
  its expected identity mapping and consumer-side source contracts.
- Remove any remaining migration recognition only after fresh source and
  installed-node readback prove no active consumer. A redirect, clean source
  scan, or repository rename alone does not satisfy that gate.

### Phase 4: Release Qualification

- Complete one system certification with temporary homes on macOS, Linux, and
  Windows/WSL, covering fresh and upgrade installs.
- For later routine releases, run fresh and upgrade on one reference platform;
  reuse the system certification unless a declared boundary change or incident
  invalidates it.
- The publisher and Framework carrier select the required qualification level;
  carrier, payload contract, Profile mutation, executor discovery, platform,
  and security changes fail closed to system certification.
- Resolve the upgrade predecessor from the public `latest-stable` observed
  before candidate promotion, never from SemVer adjacency.
- Verify Core without Linear or Fleet during system certification, then the
  optional adapters.
- Publish each OPL Flow release and perform immutable digest and live carrier
  readback appropriate to its selected qualification level.

## Maintainer Surface

The maintainer releases:

1. OPL Flow: product code, schemas, migrations, core Skills, bootstrap, doctor,
   and compatibility tests.
2. OPL Skills: optional enhancements on their own cadence.
3. OPL Instance: private data, policy, Operations Registry, and personal
   workflow changes, never public product code.

External dependencies use minimum compatible capabilities rather than pinning
every node to the controller's older version. Each node installs or upgrades
from the component owner and records the observed version.

## Completion Criteria

The consolidation is complete only when:

- a new user can install OPL Flow and initialize Core through one guided action;
- one private instance contains the durable Ledger, private policy, and
  Operations Registry;
- public workflow behavior has one source owner in OPL Flow;
- OPL Fleet is usable without understanding a separate public repository;
- OPL Skills is optional;
- every renamed remote and installed node reads back the new canonical owners;
- old repositories contain no unique authority and can be archived without
  losing source, state, or recovery evidence.
