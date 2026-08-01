# Ledger Start

Use this reference only after reading `start-onboarding.json`.

`OPL Ledger` is the owner Instance's complete human work ledger. It is not the
Supervisor itself and is not limited to OPL repository development. Installing
Flow, running `setup`, or running `update` only deploys or maintains capability;
formal onboarding happens only after explicit `$opl-flow start`.

## Idempotent Onboarding

1. Resolve the current saved project, local environment, unique private
   Instance, and objective fingerprint. Ask only on material ambiguity.
2. Use native Codex project/task tools to reuse one matching Dashboard and pin
   it. Create only when none exists; multiple matches fail closed.
3. Pull the Instance Ledger. Reuse the Bead whose `external_ref` is exactly
   `codex://thread/<thread_id>`, or create one when absent. Never initialize a
   second Ledger.
4. Parse `$CODEX_HOME/automations/*/automation.toml` to discover the one hourly
   heartbeat bound to the Dashboard and objective. Unreadable or ambiguous
   discovery fails closed. Use native Automation view/update; never create a
   cron workaround or second loop.
5. Configure the fixed display name `OPL Flow Supervisor`, not a passive
   poller. One heartbeat supervises one or more registered Linear projects;
   adding a project updates the existing Supervisor rather than creating a
   second heartbeat. Register `OPL Ledger` by default.
6. Each run reads ready,
   in-progress, overdue, and live execution tasks; chooses one allowed decision
   per lane; performs continuation, correction, split, merge, idle-event, or
   terminal review; and writes claim/checkpoint/blocker/remaining to Beads.
   Before remote dispatch, read the Bead's single
   `metadata.opl_execution_requirements` object. If absent, keep execution in
   the current Codex session. If present, validate it against
   `contracts/execution-requirements.schema.json`, then use `$opl-fleet` for
   plan, fresh admission, lease, adapter execution, result readback, and
   release. Record only the dispatch ID and short outcome in the Bead; never
   store lease nonces, private routes, command output, or credentials.
7. Reconcile every user-ledger Bead to exactly one Linear issue through the
   official Connector, preserving hierarchy and the narrow field contract.
8. For each registered project, call
   `mcp__codex_apps__linear_list_comments`, consume authorized user comments
   after its saved Linear comment-ID high-watermark, and send each new comment
   exactly once to the corresponding local Codex task using the comment ID as
   the idempotency key. Advance the cursor only after successful delivery or a
   documented non-user ignore. Ignore Supervisor, Agent, Automation, and other
   non-user comments. Process comments no later than the next heartbeat. A
   Cloud delegate is a conflict and fails closed.
9. Register Ambient Ops as an OPL Fleet observability extension inside the
   current Ledger; do not create another heartbeat.
10. Push and read back Dolt only after coherent mutation. Finish with exact
    Dashboard, Bead, heartbeat, registered-project, comment-cursor/delivery,
    Ambient Ops, Linear coverage, and Dolt parity.

## Linear Field Authority

Linear to Beads: human intent, priority, due, optional compatibility
`codex-ready`, explicit opt-out `codex-paused`, and cancel.

Beads to Linear: execution state, blocker, result.

Beads lifecycle and visible execution activity are separate. Keep the durable
lifecycle in the native Beads status and store exactly one current
`metadata.execution_mode`: `active`, `waiting_user`, `waiting_external`,
`monitoring`, or `aggregate`. Linear displays `Waiting` for started work that
is blocked on a user, dependency, or external event, and `Monitoring` for a
continuous responsibility with no current execution action. When Linear is
read back, `Waiting` preserves a Bead already in `blocked`; otherwise it keeps
`in_progress`. `Monitoring` normalizes to `in_progress`; only genuinely
unstarted work displays `Todo`.

Aggregate issues roll up descendants: an active descendant displays `In
Progress`; waiting-only descendants display `Waiting`; monitoring-only
descendants display `Monitoring`; no unresolved descendants displays `Done`.
Unknown or ambiguous execution mode fails closed without changing Linear.

Project only identity, title, hierarchy, status, priority, due, readiness,
execution mode, display status, cancel intent, short blocker/result, and links. Exclude credentials, local
paths, logs, full notes, metadata, and checkpoints. Do not use `bd linear sync`.

Every issue in a registered project is managed by local Codex by default.
`codex-ready` may remain for compatibility but is not required on every issue.
`codex-paused` blocks dispatch only; Linear reconciliation and authorized user
comment intake continue so resumption does not lose human intent.

Beads/Dolt is task SSOT. Linear is the complete human-readable projection;
GitHub carries delivery evidence; Fleet carries capacity and the optional
Ambient Ops observability extension. Do not use Codex Cloud or Cloud delegate
for this route and do not archive without fresh user approval.

## Execution Requirement Authority

Beads owns task intent through `metadata.opl_execution_requirements`. Fleet
owns observed capacity and the controller lease. The execution adapter owns the
bounded result readback. These are one transaction, not three schedulers.

Use `gpu_api=cuda` for NVIDIA CUDA work and `gpu_api=metal` for Apple GPU work.
Apply `min_gpu_memory_gb` and `gpu_model` only when the task genuinely depends
on them. Do not encode a preferred machine: nodes with equivalent policy remain
peers, and selection follows fresh availability, admission, and concrete
requirements.
