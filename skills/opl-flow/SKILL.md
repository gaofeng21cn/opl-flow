---
name: "opl-flow"
description: "Use when installing, syncing, diagnosing, or explaining the OPL Flow workflow profile, or when the user explicitly asks to use OPL Flow. OPL Flow keeps normal development model-native and does not bootstrap a development methodology."
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

Current source ownership is intentionally explicit: Flow `0.1.29` bundles
`opl-flow` and `coordinate-concurrent-tasks`; `develop-and-deliver`,
`task-mode-gate`, and `recover-codex-tasks` remain in OPL Skills until their
single-source migration is completed. `architect-and-simplify` remains an
optional enhancement.

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
- Update optional Fleet nodes from each component owner and verify them only
  when Fleet is configured. Linear sync starts with the official Beads dry-run.

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

Linear remains an optional Beads-native human portal:

```bash
(cd <opl-instance> && bd linear status --json)
(cd <opl-instance> && bd linear sync --dry-run --json)
```

Use `LINEAR_API_KEY` or Beads-supported OAuth environment variables. Never
write those values to Git, Beads issue text, logs, or Flow configuration.

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
