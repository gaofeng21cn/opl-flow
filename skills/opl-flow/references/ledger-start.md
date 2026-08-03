# Ledger Start

Use this reference only for explicit `$opl-flow start`. `OPL Ledger` is the
owner Instance's complete human work ledger, not the Supervisor or an OPL-source
project list. Setup, update, and install never run this route.

## Idempotent Onboarding

1. Resolve the saved Codex project, local environment, unique private Instance,
   and objective fingerprint. Ask only on material ambiguity.
2. Discover the native thread-owner tools and inspect their current schemas
   before enumeration. Use `list_threads` with a schema-valid bound; until the
   owner schema advertises a different maximum, never pass a `limit` greater
   than `50`. If the known Ledger set exceeds the returned window, read the
   exact saved thread IDs and report intake coverage as incomplete instead of
   inferring absence. Match `(project_id, objective_fingerprint)`, reuse one
   Dashboard, use `create_thread` only for zero matches, and fail closed on
   multiple matches. Pin it with `set_thread_pinned`, then `read_thread` the
   exact project, thread ID, title, and pinned state. Classify native failures
   precisely: `invalid_arguments` is a caller defect to correct,
   `permission_denied` requires owner authorization, `timeout_unknown` requires
   read-only reconciliation, and `unavailable` is reserved for a missing
   capability or an owner response that explicitly says unsupported or
   unavailable. Never collapse these states into a generic tool blocker.
3. Run `bd dolt pull`, then use the owner `bd` CLI to reuse the one Bead whose
   `external_ref` is exactly `codex://thread/<thread_id>` or create it when
   absent. Multiple matches fail closed; never initialize a second Ledger.
4. Use `automation_update` view to match
   `(kind=heartbeat, target_thread_id, objective_fingerprint)`. Create only for
   zero matches, update one match, and fail closed on unreadable or multiple
   matches. Read back one active hourly heartbeat named exactly
   `OPL Flow Supervisor`; all registered Linear projects share it.
5. Each Supervisor run uses `list_threads` and a saved intake cursor to classify
   unseen or changed local tasks as `managed_objective`, `ephemeral_operation`,
   or `persistent_workbench`. Development and delivery objectives are managed
   by default. A short manual operation is excluded unless the user explicitly
   promotes it or it leaves a durable cross-session obligation. A persistent
   workbench or controller is excluded from task completion and Linear issue
   counts; keep its root task in `MONITORING` and manage only its concrete child
   objectives. Save the stable classification and short reason in Dashboard
   internal metadata so later runs do not repeatedly reclassify it.
6. For every managed objective and registered persistent workbench, use
   `read_thread` and the current owner surface to reconcile real execution,
   canonical Git/public/runtime state, blockers, remaining work, and the task
   title. Update Beads and Linear from those facts; never use a stale title,
   spinner, callback, checkpoint, PR, or local branch as proof of canonical
   completion. The Supervisor may report or route product-SSOT drift, but it
   never merges, publishes, deploys, or overwrites another owner's authority.
7. Each Supervisor run reads ready, in-progress, overdue, and live managed
   tasks, acts on current user intent, and records
   claim/checkpoint/blocker/remaining in Beads. Before remote dispatch, read the Bead's single
   `metadata.opl_execution_requirements` object. If absent, keep execution in
   the current Codex session. If present, validate it against
   `contracts/execution-requirements.schema.json`, then use `$opl-fleet` for
   plan, fresh admission, lease, adapter execution, result readback, and
   release. Record only the dispatch ID and short outcome in the Bead; never
   store lease nonces, private routes, command output, or credentials.
8. Reconcile every user-ledger Bead to exactly one Linear issue through
   `mcp__codex_apps__linear_list_issues`, `mcp__codex_apps__linear_get_issue`,
   and `mcp__codex_apps__linear_save_issue`. Read before write and read back
   after write; preserve hierarchy and the narrow field contract. Do not use
   `bd linear sync`.
9. For every projected issue, use `mcp__codex_apps__linear_list_comments` and
   the registered project's saved comment-ID cursor. Track each later comment
   through `observed -> delivery_pending -> delivered -> owner_answered ->
   reply_pending -> replied -> cursor_advanced`, with `delivery_unknown` as a
   reconcilable branch rather than a synonym for unavailable. Before sending,
   use `read_thread` to look for the exact marker
   `linear_comment_id=<comment_id>`. If absent, call `send_message_to_thread`
   once with that marker and the comment ID as the idempotency key, then use
   `wait_threads` or `read_thread` to confirm receipt and obtain the local task
   owner's actual answer. If dispatch times out or returns an unknown result,
   do not retry until a fresh destination read proves the marker absent; allow
   at most one bounded retry and preserve `delivery_unknown` if reconciliation
   remains inconclusive.

   Reply to the original Linear comment through
   `mcp__codex_apps__linear_save_comment`, then read the reply back before
   advancing the cursor. Because the connector may publish through the same
   authenticated Linear user identity as the human, every automated reply must
   start with a prominent locale-appropriate marker equivalent to
   `🤖 **Automated Codex reply | OPL Flow Supervisor**`, followed by the source
   `codex://thread/<thread_id>` and a short provenance statement that says
   whether the answer came from owner readback, newly executed work, or another
   named authority. A footer-only attribution is insufficient. Treat this
   marker as non-user provenance even when the author account is the same, so
   the Supervisor cannot ingest its own reply as new human intent.

   Advance the cursor only after destination receipt, owner answer, marked
   Linear reply, and reply readback, or after a recorded non-user ignore. A
   title/status update is not comment completion. Ignore Supervisor, Agent,
   Automation, and other non-user comments. `codex-paused` stops dispatch only;
   reconciliation and comment intake continue. A Cloud delegate is a conflict
   and fails closed.
10. Keep Ambient Ops inside this Ledger as an OPL Fleet observability extension;
   it never creates another Supervisor or heartbeat.
11. After one coherent mutation, run `bd dolt push`, then pull and read the
   affected Beads again. A real no-change result is valid; unknown parity is
   not.

## Fresh Acceptance

Do not build a parallel receipt. Complete `start` only when the same run reads:

- `read_thread`: the one pinned Dashboard and exact project/thread identity;
- `bd show --json`: one Bead with the exact `codex://thread/<thread_id>` link
  and its saved per-project comment cursor;
- `automation_update` view: one active hourly `OPL Flow Supervisor`, targeting
  that thread, bound to the objective fingerprint, and containing the complete
  registered-project set;
- native tool preflight plus `list_threads` with a schema-valid bound and
  Dashboard metadata: every newly observed task has one stable intake
  classification; excluded operations/workbenches created no Bead or Linear
  issue, while managed objectives have one of each; incomplete enumeration or
  `timeout_unknown` is reported precisely rather than as unavailable;
- `read_thread` plus owner authority readback: managed task facts, aggregate
  counts, and titles match actual execution and canonical state; no task was
  archived automatically;
- Linear `list_issues`/`get_issue`: one current issue per Bead after write;
- Linear `list_comments` plus the destination task's `read_thread`: every
  authorized comment after the saved cursor is delivered once, answered by the
  task owner, replied to in the original Linear thread with the prominent
  automated-Codex provenance marker, and read back; every skipped comment is
  non-user, and the Beads cursor matches the last fully handled comment;
- `bd dolt pull` after push or explicit no-change: no remaining remote drift.

Repeating `start` must return the same Dashboard, Bead, and heartbeat IDs and
must create zero duplicates. Any missing, stale, unreadable, or ambiguous
readback leaves the action incomplete.

## Thread Intake And Titles

Automatic Ledger enrollment is purpose-based, not a blanket rule for every
conversation:

- `managed_objective`: finite development, delivery, release, research, or
  other project work with an owner and verifiable outcome. Software development
  belongs here by default and receives one Bead plus one Linear issue.
- `ephemeral_operation`: short manual maintenance or interactive troubleshooting
  that should finish in its current task. Do not enroll it automatically. If it
  later creates an explicit deadline, recurring duty, external dependency, or
  user-requested follow-up, enroll only that durable follow-up objective.
- `persistent_workbench`: a mail workbench, digital-persona controller, or other
  long-lived intake surface used intermittently. Do not treat the root task as
  a finite objective or include it in open-issue counts. Keep it available as
  `MONITORING`; enroll concrete child objectives separately.

A durable responsibility is not by itself a `persistent_workbench`. When a
bounded execution episode finishes and only a future due date or event trigger
remains, keep the durable Bead and Linear issue in `monitoring`, clear the live
`metadata.execution_thread`, and retain the completed thread only as
`metadata.last_execution_thread` provenance. Store a machine-readable due date
and short trigger set on the Bead. Mark the completed executor
`SAFE_TO_ARCHIVE`, and archive it only after fresh user approval. When a due
date or trigger fires, create or resume one bounded executor, bind it as the
current `execution_thread`, and clear that binding again after authoritative
result readback. Do not keep an idle task open merely to represent the durable
responsibility, and do not create a second Supervisor or heartbeat.

Use task titles as a human-readable projection only: `ACTIVE` for live work,
`NEEDS_ACTION` for a required user login/decision/authorization, `BLOCKED` for
an external dependency, `MONITORING` for a persistent workbench or supervisor,
and `SAFE_TO_ARCHIVE` only after authoritative terminal readback. Updating a
title never archives the task and never changes product SSOT.

## Linear Field Authority

Linear to Beads: human intent, priority, due, optional compatibility
`codex-ready`, explicit opt-out `codex-paused`, and cancel.

Beads to Linear: execution state, blocker, result.

Beads lifecycle and visible execution activity are separate. Keep the durable
lifecycle in the native Beads status and store exactly one current
`metadata.execution_mode`: `active`, `waiting_user`, `waiting_external`,
`monitoring`, or `aggregate`. Linear displays `Needs Action` when the owner's
login, decision, or authorization is the next step; it displays `Blocked` when
an external event or dependency prevents progress. Neither state keeps an Agent
allocated. `Monitoring` also allocates no Agent unless a bounded execution
episode is currently bound. When Linear is read back, both preserve a Bead
already in `blocked`; otherwise they keep `in_progress`. `Monitoring`
normalizes to `in_progress`; only genuinely unstarted work displays `Todo`.

Aggregate issues roll up descendants: an active descendant displays `In
Progress`; otherwise owner action takes precedence over external blocking,
which takes precedence over monitoring. No unresolved descendants displays
`Done`. Unknown or ambiguous execution mode fails closed without changing
Linear.

Project only identity, title, hierarchy, status, priority, due, readiness,
execution mode, display status, cancel intent, short blocker/result, and links.
Exclude credentials, local paths, logs, full notes, metadata, and checkpoints.

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
