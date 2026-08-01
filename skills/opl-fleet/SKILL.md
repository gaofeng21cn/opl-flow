---
name: "opl-fleet"
description: "Use when configuring, inspecting, admitting, selecting, leasing, synchronizing, or dispatching work across OPL Fleet machines backed by a private OPL Instance."
---

# OPL Fleet

OPL Fleet is Flow's reusable multi-machine engine. It consumes an explicit
private OPL Instance; it does not own node topology, credentials, personal
policy, private assets, sessions, logs, or runtime databases.

## Route

Use the package-root engine directly or through `opl_workflow.py`:

```bash
python3 scripts/opl_fleet.py --instance <opl-instance> status
python3 scripts/opl_workflow.py fleet --instance <opl-instance> status
```

Choose the narrow command family:

- `status`: read Fleet/controller state.
- `doctor <node_id>`: fresh admission before dispatch.
- `nodes`, `inventory`, `assets`: inspect declared/private resources through
  sanitized contracts.
- `repos status|sync`: verify or reconcile repository currentness.
- `select`: choose a node from fresh capabilities and policy.
- `lease`: acquire, verify, renew, release, or reconcile protected capacity.
- `dispatch`: plan, acquire, verify, execute, or release one adapter-bound
  execution transaction.
- `runner`: execute the guarded runner transaction.
- `join` or `reconcile`: enroll or update node-local behavior through the
  Instance policy and owner routes.

Read `python3 scripts/opl_fleet.py <command> --help` for exact options rather
than guessing flags.

## Dispatch

Use the explicit dispatch transaction when a task needs remote or protected
capacity:

```bash
python3 scripts/opl_fleet.py --instance <opl-instance> dispatch plan \
  --requirements-json @execution-requirements.json
python3 scripts/opl_fleet.py --instance <opl-instance> dispatch acquire \
  --requirements-json @execution-requirements.json \
  --owner-task <task-id> --owner-thread <thread-id> --owner-run <run-id>
python3 scripts/opl_fleet.py --instance <opl-instance> dispatch verify <dispatch-id>
python3 scripts/opl_fleet.py --instance <opl-instance> dispatch execute <dispatch-id> \
  --owner-task <task-id> --owner-thread <thread-id> --owner-run <run-id> \
  --argv-json '["command", "argument"]'
python3 scripts/opl_fleet.py --instance <opl-instance> dispatch release <dispatch-id> \
  --owner-task <task-id>
```

Store task intent in the Bead's `metadata.opl_execution_requirements` object,
using `contracts/execution-requirements.schema.json`. Pass that same object to
`plan` and `acquire`; do not create a second dispatch database. For example:

```json
{
  "schema": "opl_execution_requirements.v1",
  "adapter": "ssh-session",
  "requires": ["windows", "wsl"],
  "min_memory_gb": 32,
  "gpu_api": "cuda",
  "min_gpu_memory_gb": 20,
  "gpu_model": "RTX 4090",
  "workload_class": "background",
  "priority": 300,
  "preemptible": true,
  "phase": "interruptible",
  "ttl_seconds": 3600
}
```

`plan` is candidate readback only. `acquire` runs fresh admission and takes the
controller lease; `verify` and `release` use the private lease store and owner
CAS. An offline or ineligible node is skipped, and no eligible node returns
`unavailable` rather than a fabricated execution result.

Adapter boundaries are explicit:

- `local-codex` executes in the current session and takes no Fleet lease;
- `lease-only` reserves capacity for a caller-owned executor;
- `github-runner` uses the existing guarded runner transaction but does not
  submit a GitHub job;
- `ssh-session` runs one structured argv through the Instance's private SSH
  route after lease verification; Windows routes execute inside WSL;
- `remote-codex` remains planned and fails closed.

`ssh-session` never accepts a joined shell command. It returns bounded
stdout/stderr and an exit code without storing them in the repository or lease
store. A transport failure is `unknown`: retain the lease, reconcile read-only,
and do not retry automatically. A known result still requires an explicit
owner release.

## Invariants

1. Resolve one explicit Instance root containing `fleet/fleet.json` and
   `fleet/nodes.json`. Material ambiguity fails closed.
2. Static inventory is desired state, not availability. Run fresh `doctor`
   admission before selection or dispatch.
3. Every protected lease binds adapter, owner task/thread/run identity,
   requirements, GPU constraints, priority, expiry, and a safe
   release/reconciliation route.
4. Pull/fetch current repository state before sync or dispatch. Do not copy a
   controller checkout, installed binary, Skill tree, credential, or session to
   another node.
5. Each node installs and updates components from their current owners and may
   run a different compatible version.
6. Keep Fleet capacity separate from task truth. Beads/Dolt owns durable work;
   GitHub owns delivery evidence; Fleet owns only execution admission/capacity.
7. Record sanitized receipts in the Instance. Never commit secrets, private
   addresses, exhaustive raw inventory, logs, caches, or runtime databases.
8. Never report a plan, lease, online runner, or dispatch receipt as proof that
   the caller-owned workload executed; require the executor's result readback.

## Terminal Readback

For a read-only request, report the exact Instance, node, fresh admission,
capabilities, repository currentness, and active lease/runner state.

For a mutation, read back the owner-authoritative Instance receipt and target
node state. An accepted command, local process, static node record, or planned
lease is not completion. If a remote result is unknown, reconcile read-only
before any retry.
