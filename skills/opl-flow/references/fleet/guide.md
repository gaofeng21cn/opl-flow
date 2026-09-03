# OPL Fleet

OPL Fleet is Flow's Agent-native distributed execution and task-continuity
engine for heterogeneous machines. It consumes an explicit private OPL
Instance and reuses SSH, GitHub Runner, native Codex connections, HPC, cloud,
container, or workflow systems as execution adapters where appropriate.

The durable objective and current execution owner remain in Beads/Dolt.
GitHub owns code currentness, recoverable checkpoints, and delivery evidence.
Fleet owns workspace currentness, node admission, protected capacity, and the
adapter-bound execution attempt. A Codex task or thread is a replaceable
executor handle; Fleet does not own node topology, credentials, personal
policy, private assets, sessions, logs, or runtime databases.

A control Agent may turn natural-language intent into a Ledger-owned dynamic
task graph and supervise worker Agents through Fleet. Fleet manages versioned
context references and recovery boundaries, never raw conversation storage.
For a registered Ledger objective, a fresh authorized user message on its
provenance or execution task is a dispatch/reconciliation event even when the
objective is externally blocked or review-backoff is not due; the controller
must re-read the task and decide whether to reply, repair, or update projection.
Fleet does not hard-code product exclusions; the Supervisor's dynamic
responsibility registry decides whether a discovered item is personal work,
another owner's work, or still under intake review before any Ledger admission
or dispatch.
Deterministic contracts guard identity, scoped permission, time/token/cost and
resource budgets, leases, checkpoints, and terminal readback; "Agent manages
Agent" never grants unconstrained autonomy.

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
- `data-job`: run a lightweight per-node task and optionally fetch one
  HOME-relative artifact directory without reserving compute capacity.
- `runner`: execute the guarded runner transaction.
- `join` or `reconcile`: enroll or update node-local behavior through the
  Instance policy and owner routes.

Read `python3 scripts/opl_fleet.py <command> --help` for exact options rather
than guessing flags.

Workspace bootstrap/currentness and execution-owner migration are active source
work, not current public behavior. Do not invent their commands or report them
as available until they appear in current `--help` output and pass canonical
source plus real cross-machine readback.

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
- `remote-codex` requires fresh sanitized Codex desktop-host and login-startup
  readback, then uses the native Codex App task connection after lease
  verification. The Fleet CLI never accepts or stores a pairing code, prompt,
  session, or task result.

For `remote-codex`, do not call `dispatch execute`. After `acquire` and
`verify`, select the matching connected Codex host through the native app. Start
a new task in an existing saved project when the user explicitly requested a
new task; otherwise continue or hand off an existing task on that exact host.
Wait for the remote task's terminal result, read it back, and only then call
`dispatch release`. Device connection, lease acquisition, task creation, and
message acceptance are intermediate states, not workload completion.

`ssh-session` never accepts a joined shell command. It returns bounded
stdout/stderr and an exit code without storing them in the repository or lease
store. A transport failure is `unknown`: retain the lease, reconcile read-only,
and do not retry automatically. A known result still requires an explicit
owner release.

Use `data-job run` for low-impact fan-out work such as analytics projections
that must cover every current managed node even while the node is interactive:

```bash
python3 scripts/opl_fleet.py --instance <opl-instance> data-job run <node-id> \
  --argv-json '["python3", "-"]' \
  --stdin-file task.py \
  --artifact-path .local/state/example/output \
  --artifact-destination ./imports/<node-id>
```

Data jobs require approved, current nodes with fresh inventory, Python, and a
fresh Fleet SSH/Tailscale route. They deliberately ignore compute scheduling,
interactive-idle, GPU, and protected-capacity gates. Fleet treats argv, stdin,
and the artifact directory as generic task inputs; the caller owns their schema
and terminal interpretation.

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
6. Keep Fleet attempts and capacity separate from task truth. Beads/Dolt owns
   the objective and current execution owner; GitHub owns code currentness,
   checkpoints, and delivery evidence; Fleet owns workspace currentness,
   execution admission/capacity, and adapter invocation.
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
