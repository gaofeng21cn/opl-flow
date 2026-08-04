# Ledger Supervisor Episode

Use this reference for one bounded `OPL Flow Supervisor` heartbeat. The
Automation prompt supplies only the private Instance, Dashboard Bead,
registered Linear projects, authorized human accounts, memory/cursor location,
and notification policy. This reference owns the reusable workflow.

The Supervisor is a wake-up and coordination entry, not the Ledger. Beads/Dolt
owns durable execution facts, Linear is the narrow human portal, GitHub owns
code and delivery evidence, and Fleet provides capacity only. Never create a
second heartbeat for another registered project.

## 1. Establish Fresh Local Truth

1. Read the Instance `AGENTS.md`, primary-checkout Git state, Beads/Dolt state,
   current worktrees, lifecycle receipts, holders, and owners. Do not reset,
   force, overwrite, or adopt another owner's write set.
2. Run `bd dolt pull` in the Instance primary checkout.
3. From canonical OPL Flow run:

   ```bash
   python3 scripts/opl_workflow.py ledger reconcile-operations \
     --instance <instance>
   python3 scripts/opl_workflow.py ledger supervisor-snapshot \
     --instance <instance>
   ```

4. Treat a snapshot `validation_errors` entry or exit `3` as control-plane
   drift. Fail closed for that affected Bead; do not guess a status or mapping.
5. Use the snapshot's dynamic ready set, unfinished issues, execution modes,
   dependencies, and narrow metadata. Never use a hard-coded task list.

The snapshot is read-only and intentionally excludes full notes, checkpoints,
logs, credentials, and unrelated internal metadata. It does not replace owner
readback or the official Linear Connector.

## 2. Intake Only New Or Changed Threads

Use `list_threads(limit <= 50)` and the Dashboard's durable intake cursor.
Inspect only new or recently changed local tasks. For an existing managed Bead,
`metadata.execution_thread` is its exact live index. Call `read_thread` for each
managed objective and each registered interactive longline, then corroborate
with canonical main/wire, worktree/lifecycle, release, deployment, install, or
runtime owner evidence as applicable.

Record one stable class and a short reason:

- `managed_objective`: finite development, delivery, release, research, or
  project work with an authoritative terminal outcome. Development defaults to
  this class. Enroll exactly one Bead and one Linear issue.
- `interactive_longline`: a user-returning network, operations, mail, persona,
  or other persistent workbench. It may be registered for visibility, but only
  the user archiving its Codex task is terminal. `persistent_workbench` is a
  legacy alias.
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
readback. When a product truth drift exists, continue the existing owner or
report it; the Supervisor does not merge, publish, deploy, or overwrite the
product owner.

## 3. Bounded Executors

Only a genuine workbench or the Supervisor keeps a long-lived conversation.
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

For issues changed since the stored waterline, call `linear_list_comments`.
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

When no initial waterline exists, use the Bead mapping/projected/supervised
timestamp as the lower bound. If none exists, establish the current latest
waterline without replaying all history.

Before Connector use, perform one bounded TLS health check. On a transport send
error, verify once. If it still fails, retain the last successful readback,
mark `current_transport_degraded`, and perform no guessed Linear create/update;
independent local lanes continue.

## 5. Status Projection

Keep Beads lifecycle separate from the human status projection. Every
unfinished Bead must have exactly one execution mode:

- `active`
- `waiting_user`
- `waiting_external`
- `monitoring`
- `on_demand`
- `aggregate`

For managed objectives, project:

| Beads / mode | Linear |
| --- | --- |
| `deferred` | Backlog |
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

Notify only for new intake, a processed user comment, direction correction,
first blocker, material ETA change, completion, or required user action.
Otherwise return `no_change`/`DONT_NOTIFY`. A completed episode with future due
or event-triggered work leaves the stable Bead/Linear identity in Monitoring or
On Demand and has no resident executor.
