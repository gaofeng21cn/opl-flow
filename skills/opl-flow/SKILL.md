---
name: "opl-flow"
description: "Use when starting an OPL ledger dashboard and hourly supervisor, installing, syncing, diagnosing, or explaining the OPL Flow workflow profile, or when the user explicitly asks to use OPL Flow. OPL Flow keeps normal development model-native and does not bootstrap a development methodology."
---

# OPL Flow

OPL Flow is an optional `OPL Package(kind=workflow_profile)` that distributes
the user's minimal Codex preference profile. It owns the Profile source and
intent, not OPL Base/App readiness, Package currentness, project facts,
runtime/domain truth, or another executor.

Keep project facts and procedures repo-local. Let the model handle ordinary
design and development directly.

## Route

- Use this skill to install, update, sync, explain, or diagnose the minimal
  Profile.
- Use `$opl-flow start` when the user asks to create or reuse an OPL ledger,
  management Dashboard task, or hourly supervisor. Natural language such as
  "创建 OPL 总账并每小时监督" routes to the same action.
- Use the package-root `scripts/opl_workflow.py` only for workflow status,
  Profile safety, safe Ledger initialization, Operations Registry
  reconciliation, and the optional Fleet engine. Use `bd` directly for
  ordinary ledger operations.
- Use `$coordinate-concurrent-tasks` only for evidence-driven dynamic-capacity
  multi-task ownership, parallel execution, fresh-SSOT integration, and
  archive-readiness review.
- Follow effective repo-local `AGENTS.md`, contracts, source, tests, and fresh
  readback for ordinary repository work.
- Do not make Flow a prerequisite for Base, App, Standard, Full, plain Codex,
  another Package, or domain readiness.

## One-Action Dashboard Start

When the user says `$opl-flow start` or asks to create an OPL ledger or
management task, perform the onboarding end to end. Read
`references/start-onboarding.json` first and preserve every uniqueness key,
native tool route, supervisor decision, terminal readback, and boundary in that
contract.

1. Discover the current saved project, local execution environment, and the
   unique private OPL Instance. Ask only when project, Instance, or objective is
   materially ambiguous.
2. Use Codex native project and task tools to find a Dashboard task with the
   same project and objective fingerprint. Reuse and pin one exact match;
   create a local task only when none exists. Multiple matches are a collision,
   not permission to create another task.
3. Pull the Instance Ledger and initialize it only when no Ledger exists. Find
   a Bead whose `external_ref` is exactly `codex://thread/<thread_id>`; reuse or
   update it, or create one when absent. Never initialize a second Ledger.
4. Inspect `$CODEX_HOME/automations/*/automation.toml` (or the documented
   default root when `CODEX_HOME` is unset), parse the contract-required fields,
   and use native Automation view readback before mutation. Reuse or update the
   one hourly heartbeat bound to that Dashboard and objective. Unreadable or
   ambiguous discovery fails closed; do not create a cron workaround or a
   second supervision loop.
5. Make the heartbeat supervise rather than poll. Each run pulls and
   reconciles the Ledger, reads ready, in-progress, and overdue work plus live
   execution tasks, makes one contract-defined decision per lane, and performs
   the required continuation, correction, split, merge, or terminal review.
   Write claim, checkpoint, blocker, and remaining facts to Beads. Use the
   official Linear Connector to idempotently reconcile every user-ledger Bead,
   including hierarchy, rather than only ready or active work. Missing Linear
   authorization is a real external blocker for `start`, not permission to
   accept partial coverage. Then push and read back Dolt after coherent mutation.
6. Finish by reading back the exact Dashboard thread, Bead link, heartbeat ID,
   target, active hourly schedule, Dolt parity, and Linear coverage parity.
   Linear coverage must prove that every user-ledger Bead has exactly one issue;
   report missing and duplicate counts rather than accepting partial projection.
   Dashboard, Automation, Linear, and Git branches are execution or projection
   surfaces; Beads/Dolt remains the internal task ledger. Record that readback
   as `opl_flow_start_onboarding_receipt.v1` and validate it with
   `python3 skills/opl-flow/scripts/validate_start_onboarding.py --receipt <path>`.

Linear is a complete human-readable projection of the user Ledger, but its
field set stays narrow. Use Linear's official Connector search/read/save/readback
route and preserve only Bead identity, title, hierarchy, status, priority, due,
`codex-ready`, cancel intent, short blocker/result, and links. Never project
credentials, local paths, logs, full notes, internal metadata, or checkpoints.
Human intent, priority, due, `codex-ready`, and cancel flow from Linear to
Beads; execution state, blocker, and result flow from Beads to Linear. Do not
require or use `bd linear sync` for onboarding or routine maintenance. Use
GitHub for delivery evidence and Fleet for capacity. Never use Codex Cloud for
this route, and never archive a task unless the user freshly names and approves
it.

## One-Action Setup And Update

When the user says `$opl-flow setup` or `$opl-flow update`, treat it as one
end-to-end Agent action. Do not invent an all-in-one package manager or ask the
user to manually execute every step. Ask only for unavoidable GitHub/OAuth
authorization or approval to create an external private repository.

For both actions:

1. Run `python3 scripts/opl_workflow.py status --instance <opl-instance>` when
   an Instance is known. Read Git, GitHub auth, Codex, Beads, Profile, Linear,
   and Fleet independently; a missing optional component does not fail core
   setup.
2. Resolve one private `opl-instance-<owner>` checkout. Reuse or clone an
   existing private repository. Before creating a GitHub repository, confirm
   the owner/name and private visibility with the user.
3. Install or update missing tools only from their current owner-supported
   channel. Resolve the latest compatible release on each machine; never copy
   binaries from another Fleet node or pin everyone to the controller version.
4. Preserve owner boundaries and finish with live readback. Do not treat the
   Skill prompt, Automation, Linear, a test, or a dry-run as installed truth.

### Optional OPL Skills enhancement pack

The Plugin-bundled core Skill set comes from `opl-package.json`. OPL Skills is
an independent public enhancement pack, not a required Flow dependency. When
the user explicitly asks to include public development enhancements in setup or
update, install or update them from their current owner instead of copying
their source into Flow or a private Instance:

```bash
npx skills add gaofeng21cn/opl-skills -g -a codex -s '*' -y --full-depth
```

After installation, start a new Codex session when discovery requires it and
verify the requested Skill IDs from the effective discovery surface. If a
private Instance has `contracts/skill-reference.json`, use it only to select
the user's desired owner routes; it does not make Fleet the Skill source.

Current source ownership is intentionally explicit: Flow `0.1.30` bundles
`opl-flow`, `coordinate-concurrent-tasks`, `develop-and-deliver`,
`task-mode-gate`, and `recover-codex-tasks`. `architect-and-simplify` remains
an optional OPL Skills enhancement; its absence never blocks architecture work.

For `setup`:

- A fresh Instance with no remote Ledger uses `ledger init`. A clone whose
  `.beads` metadata points to existing Dolt data uses `chmod 700 .beads`, a
  checkout-local `beads.role`, and `bd bootstrap --yes`; do not initialize a
  second Ledger.
- Run `profile prepare`. It installs a missing Profile, updates a previously
  approved source update, or returns a semantic-merge packet without changing
  an unknown existing `AGENTS.md`. Complete and review that packet before
  `profile apply --packet <path>`.
- Reconcile Operations only when the Instance owns
  `operations/registry.json`. Connect Linear and enroll Fleet nodes only when
  requested; their absence is a valid core setup.

For `update`:

- Update the installed OPL Flow through its current carrier owner, update `bd`
  through the Beads owner channel, then run `bd dolt pull` in the Instance.
- Run `profile prepare`, reconcile declared Operations, and inspect
  `bd ready --json`. Push Dolt only after a coherent Ledger mutation.
- When Linear is configured, reconcile every user-ledger Bead through the
  official Linear Connector and read back complete narrow-field parity. Update
  optional Fleet nodes from each component owner and verify them only when
  Fleet is configured.

Terminal readback includes `opl_workflow.py status`, Profile status, `bd stats`,
the applicable Dolt pull/push result, and carrier/executor discovery. Restart
the selected Codex executor when Plugin discovery requires a new session.

## Ledger, Linear, And Fleet

OPL Ledger delegates durable task state to the owner-provided `bd` CLI. It
does not reimplement Beads storage, dependency, claim, Dolt sync, or Linear
mapping. Initialize only from a clean primary checkout or standalone clone;
linked worktrees intentionally share the primary checkout's Beads database:

```bash
python3 scripts/opl_workflow.py profile status
python3 scripts/opl_workflow.py profile prepare
python3 scripts/opl_workflow.py ledger init --instance <opl-instance>
(cd <opl-instance> && bd dolt pull)
python3 scripts/opl_workflow.py ledger reconcile-operations --instance <opl-instance>
(cd <opl-instance> && bd ready --json)
(cd <opl-instance> && bd dolt push)
```

The adapter always passes `--skip-agents --skip-hooks --non-interactive` to
`bd init`; Beads must not replace the user's `AGENTS.md` or install Git hooks.
Operations tasks are deduplicated by dated `opl://operations/...` external
references. Completing a review requires updating the Registry's
`next_review_on` before the next reconciliation.

Embedded Dolt is single-writer on one machine. Pull before claiming or writing
on another machine, and push after a coherent mutation. In a new clone, set
`.beads` to mode `0700` and configure checkout-local `beads.role` before
`bd bootstrap --yes`; choose the role according to the user's authority.
`.beads/issues.jsonl` is not the cross-machine authority.

Linear remains optional for the Profile-only Core, but `$opl-flow start`
requires it for the user-ledger Dashboard. Codex maintains it through the
official Linear Connector, with exactly one
narrow-field issue for every user-ledger Bead while preserving the Bead hierarchy.
Do not use `bd linear sync` as an onboarding, routine reconciliation, or
coverage route. Connector OAuth remains outside Flow, Git, Beads issue text,
logs, and committed configuration.

When the Instance contains `fleet/fleet.json` and `fleet/nodes.json`, OPL Flow
runs its bundled generic Fleet engine. The old `codex-fleet` binary is accepted
only as a transition fallback:

```bash
python3 scripts/opl_workflow.py fleet --instance <opl-instance> status
python3 scripts/opl_workflow.py fleet --instance <opl-instance> repos status
```

The Instance owns node IDs, scheduling policy, runner bindings, private assets,
and sanitized receipts. Flow owns the reusable engine. Never infer machine
availability from static policy; use fresh `doctor` admission before dispatch.

Beads stores due/deferred state but never wakes Codex. Codex Automation, cron,
or CI owns wakeup; OPL Flow owns idempotent reconciliation; Codex owns task
creation, reasoning, execution, and native multi-agent coordination.

## Package, Publication, Carrier, Executor

Keep the three runtime layers separate and treat publication as an independent
axis:

```text
Package     = opl-flow identity and capabilities
Publication = owner source/tag and official GHCR bytes/current alias
Carrier     = local install/update/remove and fresh installed readback
Executor    = discovery and execution route for installed capabilities
```

GHCR is a publication store/source, not a carrier. Codex Plugin Manager and
Codex CLI are the only formal carrier/executor production path today. Keep
Package identity, Profile, preferences, tasks, and public status/actions
OPL-owned so a future executor adapter can change without reinstalling Flow.
A minimal Git/local neutral adapter proof may verify that boundary; it is not a
second supported carrier or executor product.

Normal dependencies are stable identity presence/callability. Do not require
SemVer/ABI resolution, lock, payload, receipt, digest, provenance, or a shared
release cohort. Breaking interfaces use a new identity or owner-side adapter.

## Install And Verify

Use the currently executable Framework compatibility route:

```bash
opl packages install opl-flow
opl packages update opl-flow
```

The current implementation may still return resolver, lock, payload, receipt,
rollback, or provenance fields. Treat those as transitional implementation
readback, not target composition gates.

Existing compatibility code may describe dependency selection as an
`available compatible source`. Read that phrase as the current adapter route;
the target only needs identity presence/callability and does not add a central
version or provenance solver.

The target official online source is the Flow owner's per-Package GHCR
`opl-flow:latest-stable`. The shared `one-person-lab-manifest:latest-stable`
serves only Full/offline/integration-test/QA snapshots. GHCR does not install
the Package or define local truth. A thin Base OCI adapter may download, verify,
and hand off bytes; the configured carrier performs install/update/remove and
fresh readback. Codex owns Plugin/config/cache, while the complete Flow Package
still needs carrier installed readback.

`scripts/install_local_plugin.py` is only a repository developer/local-source
tool. It is not ordinary installation or Package currentness authority.

## Profile Safety

Installed user surfaces:

- Runtime profile: `~/.codex/AGENTS.md`
- Non-runtime authoring source: `~/.codex/TASTE.md`

For an existing `AGENTS.md`, preserve these invariants:

1. hash the original target;
2. back it up before mutation;
3. remove only known marker blocks and preserve distinct preferences;
4. compare the target SHA immediately before apply;
5. validate and atomically replace, otherwise leave the original untouched.

If semantic merge cannot be validated, follow the review/apply fallback route returned by the package command.
Current compatibility implementations may use a merge packet and rollback
receipt. Do not generalize that Profile-specific safety into a Package
lock/payload/receipt requirement.

The public Profile owner surface is:

```bash
python3 scripts/opl_workflow.py profile status
python3 scripts/opl_workflow.py profile prepare
python3 scripts/opl_workflow.py profile apply --packet <reviewed-packet>
```

`prepare` never overwrites an unknown existing `AGENTS.md`; it returns a
semantic-merge packet and exit status 2 until reviewed output is ready.

Restart the selected executor when its discovery requires refresh.

## App Boundary

Flow can be a default root in the single App Official Profile, but the Profile
runs only at first install or explicit Restore. Standard installs online; Full
may use an offline seed. If the user uninstalls Flow, startup, daily maintenance,
and App updates must not reinstall it.

OPL App must not parse Flow's companion Skill/Tool/Plugin/MCP list or keep a
second model inventory. It consumes only Framework's generic projection of
actual carrier state. Missing Flow or a dependency is local to Flow.

Use model precedence:

```text
explicit user selection
> installed Flow recommendation
> fresh executor default
> App fallback when Flow is unavailable
```

Never bundle credentials or overwrite unknown user/third-party MCP
configuration.

## Repo Profile Sync

```bash
python3 scripts/repo_profile.py check --repo-root <repo-root>
python3 scripts/repo_profile.py sync --repo-root <repo-root>
python3 scripts/repo_profile.py sync --repo-root <repo-root> --apply
```

`sync` is dry-run unless `--apply` is provided. Apply mode updates only the
profile contract and removes known legacy Flow marker blocks. Repo-local
instructions remain entirely repository-owned.

## Readback Boundary

Read these independently:

1. owner source/tag and per-Package GHCR `latest-stable`;
2. complete Package installed/healthy state from the local carrier;
3. selected executor discovery and callability;
4. exact Full/QA snapshot when that build is in scope.

During migration, the compatibility checks are:

```bash
opl packages list --json
opl packages status --package-id opl-flow --json
codex plugin list --json
```

An owner tag, shared manifest, Framework lock, Plugin payload, docs, or tests
cannot prove all four layers. `install_local_plugin.py --verify-only` proves
only the local Codex development carrier.

The target boundary and current migration gap are documented in
`docs/capability-governance.md` and `docs/status.md`. Do not claim migration
complete until actual install/update/remove, Standard/Full, Profile safety,
complete Package, the formal Codex route, and the evidence-driven Git/local neutral
contract proof all pass. Do not build or imply a second executor product merely
to satisfy that proof.
