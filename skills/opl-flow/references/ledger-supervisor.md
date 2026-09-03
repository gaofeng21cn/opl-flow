# Ledger Supervisor Episode

Use this reference for one bounded `OPL Flow Supervisor` heartbeat. The
Automation prompt supplies only the private Instance, Dashboard Bead,
registered Linear projects, authorized human accounts, memory/cursor location,
and notification policy. This reference owns the reusable workflow.

The Supervisor is a wake-up and coordination entry, not the Ledger. Beads/Dolt
owns durable execution facts, Linear is the narrow human portal, GitHub owns
code and delivery evidence, and Fleet provides capacity only. Never create a
second heartbeat for another registered project.

Responsibility is dynamic, not a hard-coded repository or product exclusion.
Maintain a responsibility registry in the private Supervisor memory with one
entry per observed work item classified as `personal_responsibility`,
`other_owner`, or `intake_review`. Each entry requires source/thread identity,
authority or delegation evidence, current owner, write-set boundary, and
`last_verified_at`. Only `personal_responsibility` entries may enter Beads,
Linear, or Dashboard counts; `other_owner` is associated evidence only; unclear
ownership remains `intake_review` without task creation or projection. Refresh
the registry every Phase A and whenever user or owner direction changes.

A generic continuation such as `continue` or `继续` advances only the current
owner after a fresh owner read. It is not new authorization for a secret,
deployment, release, destructive mutation, or execution-owner transfer. When
that owner is active, preserve it as the sole writer and do not start a parallel
action.

## Control Plane Separation

Use an event-driven three-layer control plane:

- The global Supervisor owns Ledger reconciliation, macro coordination, and
  exception fallback. A scheduled episode is only a bounded change detector;
  it never becomes a product execution loop.
- Each product controller owns its objective graph, accepts executor results,
  fixes the first real blocker, and dispatches the next bounded slice. When the
  breakpoint, owner, and write set are already known, its first production
  action is the owner-side repair or a traceable delivery bridge; tests and
  callbacks only prove or recover that repair. This is a logical product
  responsibility, not a requirement for another resident polling conversation.
- Each executor owns one bounded slice and calls its product controller on a
  recoverable checkpoint, terminal result, or real blocker. The product
  controller handles that callback in the same episode by accepting the
  evidence, repairing the blocker, or dispatching the successor.

A callback is a wake-up signal and provenance, not proof of completion. The
product controller still verifies owner, write set, checkpoint, canonical
absorption, runtime/publication state, and cleanup as applicable. The global
Supervisor intervenes only when an executor is lost, a required callback is
missing, or cross-objective owner/write-set conflict appears. With no event,
perform no product read, successor dispatch, or semantic write.

## 1. Run The Bounded Change Detector

Phase A establishes enough fresh truth to decide what needs expansion. It does
not reread every task, worktree, holder, release, deployment, install, or
runtime owner on every heartbeat.

1. Read the effective Instance `AGENTS.md` and this policy. Keep the private
   Supervisor memory/cursor location as the durable observation-state owner.
2. Run `bd dolt pull` in the Instance primary checkout, then from canonical OPL
   Flow run:

   ```bash
   python3 scripts/opl_workflow.py ledger reconcile-operations \
     --instance <instance>
   python3 scripts/opl_workflow.py ledger supervisor-snapshot \
     --instance <instance>
   ```

3. Treat a snapshot `validation_errors` entry or exit `3` as control-plane
   drift. Fail closed for that affected Bead; do not guess a status or mapping.
4. Use the snapshot's dynamic ready set, unfinished issues, execution modes,
   dependencies, narrow metadata, and `counts.semantic`. Treat raw `unfinished`
   as the Beads row count; use `semantic.unfinished_tasks` for real tasks and
   `semantic.aggregate_control_planes` for Dashboard/portal control planes.
   Never use a hard-coded task list or manually recompute these counts.
5. Call `list_threads(limit <= 50)` once. Compare only `updatedAt`, `status`, and
   `hasUnreadTurn` with the saved per-thread observation. Do not use the title as
   an observation signature: it is a Supervisor-maintained projection.
   For every changed thread that is the registered provenance or execution task
   of a personal-ledger objective, inspect newly arrived user messages during
   the same episode. An authorized human message is an immediate event even when
   the Bead is `waiting_external`/Blocked or its `next_review_at` backoff is not
   due; it must trigger exact reconciliation and a reply or status projection.
6. Do not call `wait_threads` merely because a live
   `metadata.execution_thread` exists. Normal progress arrives as an executor
   callback to the product controller. Use `wait_threads(timeoutMs=0)` in
   batches of at most eight only during Phase B after `executor_lost`,
   `callback_missing`, or a cross-objective owner/write-set conflict selects an
   exact recovery target. An unchanged callback or thread summary does not
   require `wait_threads` or `read_thread`.
7. For each registered Linear project, call `list_issues` once with the saved
   project `updatedAt` waterline. For every issue returned by that delta, call
   `linear_list_comments` before concluding that no authorized comment exists
   or advancing the project waterline. Do not read comments for an unchanged
   issue.

The snapshot is read-only and intentionally excludes full notes, checkpoints,
logs, credentials, and unrelated internal metadata. It does not replace owner
readback or the official Linear Connector.

## 2. Expand Only Changed, Due, Or Ambiguous Objects

Phase B calls `read_thread` only for a new thread, changed summary, changed wait
cursor, unread turn, due review, an authorized user message on a registered
task, or ambiguous owner state. An unchanged managed
objective or registered interactive longline does not receive an hourly exact
read. When expansion is selected, corroborate only that objective with canonical
main/wire, worktree/lifecycle, release, deployment, install, or runtime owner
evidence as applicable.

Treat `executor_lost`, `callback_missing`, and cross-objective owner/write-set
conflict as recovery signals, not ordinary progress. Only the selected product
controller/executor receives exact readback; do not broaden recovery into a
fleet-wide progress poll.

For `backlog`, `waiting_external`, `monitoring`, and `on_demand`, reuse
`metadata.next_review_at` as the authority-check backoff. Before it is due, skip
the owner check unless user, owner, Linear issue, schema/policy, or relevant
repository evidence changed. Do not create a duplicate
`next_authority_check_at` field.

Do not schedule a periodic complete audit. Run one only after a missing or
ambiguous cursor, schema/policy change, `timeout_unknown`, or explicit user
request, and no more than once every 24 hours unless a current integrity
boundary requires immediate reconciliation. An unchanged observation never
proves completion, archival, delivery, or owner correctness; it only proves
that the expensive exact read is not triggered.

Record one stable class and a short reason:

- `managed_objective`: finite development, delivery, release, research, or
  project work with an authoritative terminal outcome. Development defaults to
  this class. Enroll exactly one Bead and one Linear issue.
- `interactive_longline`: a user-returning network, operations, mail, persona,
  or other persistent workbench. It may be registered for visibility, but only
  the user archiving its Codex task is terminal.
- `ephemeral_operation`: a bounded manual operation or diagnosis that normally
  ends in the current interaction. Exclude it by default; if explicitly
  enrolled, keep it record-only. Enroll any durable deadline, recurring duty,
  external dependency, or delivery as a separate managed objective.

If classification is materially ambiguous, record `intake_review` only. Do not
create a Bead/issue or rename the task. Never remove an enrolled development
objective merely because its executor is idle.

An idle title, spinner, callback, checkpoint, PR, branch, local test, or task
worktree is not SSOT. Write back the real owner, execution thread, current
slice, first blocker, next action, remaining JSON array, and authoritative
readback. If the deepest breakpoint did not move, the next action must be a
repair, delivery bridge, or real stop; do not keep the objective active with
another test or wait. When a product truth drift exists, continue the existing
owner or report it; the Supervisor does not merge, publish, deploy, or overwrite
the product owner.

## 3. Bounded Executors

Only a genuine workbench or the Supervisor keeps a long-lived conversation.
Product controllers and executors advance through direct events: executors
call back on checkpoint, terminal, or real blocker, and the product controller
accepts, repairs, or dispatches the next bounded slice in the same episode.
The global Supervisor does not resident-poll either role.

For a monitoring or on-demand objective, bind a finite executor only when its
review date, authorized user comment, or explicit event fires. After
authoritative readback:

- clear `metadata.execution_thread`;
- preserve the completed task as `metadata.last_execution_thread` provenance;
- record the next review time and trigger condition;
- never resume an archived provenance task; create a new bounded executor.

Prefer an existing live local executor. Continue an idle/error task when
remaining work is executable. Recover or create an owner only for a proven
ownerless gap. Different worktrees may run concurrently; canonical main,
release, install, database, VM, and other shared mutations require a short
single operation owner. `codex-paused` is the only explicit dispatch pause.
A Linear delegate to another Agent is a concurrent Cloud owner conflict: report
it and do not duplicate execution.

When `metadata.owner_mutation_frozen=true`, read
`metadata.opl_owner_migration` and do not resume, create, or dispatch another
executor. After the migration reaches `completed`, use the new
`metadata.execution_owner` and `metadata.execution_thread`; the previous task
is provenance only. A stale or unknown migration result is an owner ambiguity,
not an ownerless gap.

Backlog is an admitted queue, not a command to start everything. Order work by
new authorized comments, status, priority, due date, dependencies, current
owner, and available capacity. Offline machines retain an idempotent queued or
external-blocker record.

## 4. Linear Coverage And Comment Intake

Use only the official Linear Connector. Do not use `bd linear sync` in routine
supervision and do not require a Personal API Key.

For every registered project, prove one-to-one coverage between user-ledger
Beads and Linear issues. Deduplicate by the stored
`metadata.linear_issue_identifier`/URL and the Bead ID embedded in the issue
description. Never match by title. Repair a missing mapping only when identity
is exact; duplicates or ambiguous identity fail closed.

Project only: Bead ID, Chinese title, parent/child hierarchy, status, priority,
due date, short blocker/result, and GitHub/delivery links. Never project local
paths, credentials, logs, full notes, checkpoints, or internal metadata.

Project assignee is a human-accountability projection, not execution truth.
When the heartbeat supplies exactly one `authorized_human_accounts` entry,
assign every issue in every registered project, including completed issues, to
that account. If multiple accounts are configured, require an explicit
project-to-account mapping and fail closed when it is absent. During ordinary
heartbeats, inspect assignee only on issues selected by the project waterline
and repair only mismatches. Perform one full-project assignee audit only after
an explicit user request, a policy change, or a missing assignment waterline;
list the project once, filter mismatches locally, write at most ten issues per
batch, then read back the exact project issue count and zero mismatches. Never
infer `execution_owner` or `execution_thread` from Linear assignee.

For each registered project, use `linear_list_issues(updatedAt=<waterline>)` to
select changed issues. Call `linear_list_comments` for every changed issue;
an issue summary, title, timestamp, saved cursor, or prior projection never
proves that it has no new comment. Do not claim `no new comment` and do not
advance the project waterline unless every changed issue received that comment
API read. The Connector does not promise that `limit=1` is the newest comment, so
never use a smallest-page ordering assumption as the cursor gate. Page a
changed issue until the stored comment ID is found or the current changed set
is exhausted; a missing or ambiguous cursor falls back to the full audit.

Only new comments by configured authorized human accounts are user intent.
Ignore known agent comment IDs and comments whose first line is exactly:

```text
【OPL Flow · Codex 自动回复】
```

Process each human comment exactly once by stable comment ID. Deliver it to the
registered local executor, or create a bounded executor only when objective,
repository, and authority are clear. A send timeout is unknown: read the
destination thread, then retry at most once only when delivery is confirmed
absent. Advance the cursor only after destination delivery, owner answer
readback, Linear reply post, and reply readback all succeed. Store the comment
ID/time and a short result in Beads; do not copy the full comment into Git or
another Linear comment.

Advance the project issue waterline only after every selected issue has either
proved no new authorized comment or completed the delivery/reply cursor gate.
When no initial waterline exists, use the Bead mapping/projected timestamp as
the lower bound. If none exists, establish the current latest waterline without
replaying all history.

Before Connector use, perform one bounded TLS health check. On a transport send
error, verify once. If it still fails, retain the last successful readback,
mark `current_transport_degraded`, and perform no guessed Linear create/update;
independent local lanes continue.

## 5. Status Projection

Keep Beads lifecycle separate from the human status projection. Every
unfinished Bead must have exactly one execution mode:

- `active`
- `backlog`
- `waiting_user`
- `waiting_external`
- `monitoring`
- `on_demand`
- `aggregate`

For managed objectives, project:

| Beads / mode | Linear |
| --- | --- |
| `deferred + backlog` | Backlog |
| `open` | Todo |
| `in_progress + active` | In Progress |
| `waiting_user` | Needs Action |
| `waiting_external` | Blocked |
| `monitoring` | Monitoring |
| `on_demand` / pinned | On Demand |
| `closed` | Done |

Needs Action means the next step requires user login, decision, or authority.
Blocked means an external event or upstream dependency prevents progress.
Neither allocates an Agent. Preserve an existing Beads `blocked` lifecycle for
Needs Action/Blocked; otherwise preserve `in_progress`. Unknown mode or missing
Linear status fails closed and must not be guessed back to Todo.

Backlog means a finite `managed_objective` is planned but has no allocated
executor yet; capacity planning or a declared dependency release promotes it
to `active`. On Demand is reserved for a long-horizon `interactive_longline`
that the user revisits irregularly by manual or explicit trigger. Never use On
Demand for queued development, dependency waits, recovery disposition,
cleanup-only work, or completed provenance.

An interactive longline or explicitly enrolled ephemeral operation follows
fresh thread activity and cannot become Done from a bounded result,
`remaining=[]`, or a closed Bead. For aggregate parents: any active descendant
means In Progress; otherwise Needs Action outranks Blocked, Blocked outranks
Monitoring, and no unfinished descendant means Done. Write only real changes.

Human task titles are projections: `ACTIVE`, `NEEDS_ACTION`, `BLOCKED`,
`MONITORING`, or `SAFE_TO_ARCHIVE`. Only a managed objective with authoritative
terminal evidence and `remaining=[]` may receive `SAFE_TO_ARCHIVE`. Never
archive a Codex task; explicit user approval is required.

## 6. Close The Episode

Write owner, execution thread, current slice, first blocker, next action,
remaining, and terminal/readback facts to Beads. Run `bd dolt push` only when
Beads changed, then pull/read back parity. Narrowly update Linear only when a
projected field changed.

Emit compact counters for threads listed, summaries changed, wait targets,
wait cursors changed, exact thread reads, Linear projects probed, Linear issues
changed, comment pages, authority checks, writes, retries, elapsed seconds, and
any full-audit reason. For a semantic no-change episode, the expected budget is
one `list_threads`, zero `wait_threads`, one Linear issue delta call per
registered project, zero `read_thread`, zero comment calls, zero authority
checks, and zero semantic writes. Target about 60 seconds for a small Ledger.
Do not update `last_supervised_at` or another timestamp merely to prove that the
heartbeat ran.

Notify only for new intake, a processed user comment, direction correction,
first blocker, material ETA change, completion, or required user action.
Otherwise return `no_change`/`DONT_NOTIFY`. A completed episode with future due
or event-triggered work leaves the stable Bead/Linear identity in Monitoring or
On Demand and has no resident executor.
