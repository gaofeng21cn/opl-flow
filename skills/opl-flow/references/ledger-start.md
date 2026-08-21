# Ledger Start

Use this reference only for explicit `$opl-flow start`. `OPL Ledger` is the
owner Instance's complete human work ledger, not the Supervisor or an OPL-source
project list. Setup, update, and install never run this route.

## Idempotent Onboarding

1. Resolve the saved Codex project, local environment, unique private Instance,
   and objective fingerprint. Ask only on material ambiguity.
2. Preflight the native owner tools and use `list_threads` with `limit <= 50` to
   match `(project_id, objective_fingerprint)`. Keep `invalid_arguments`,
   `permission_denied`, `timeout_unknown`, and genuine `unavailable` distinct;
   never relabel one caller-schema failure as owner-tool unavailability. Reuse
   one Dashboard, use `create_thread` only for zero matches, and fail closed on
   multiple matches. Pin it with `set_thread_pinned`, then `read_thread` the
   exact project, thread ID, title, and pinned state.
3. Run `bd dolt pull`, then use the owner `bd` CLI to reuse the one Bead whose
   `external_ref` is exactly `codex://thread/<thread_id>` or create it when
   absent. Multiple matches fail closed; never initialize a second Ledger.
4. Use `automation_update` view to match
   `(kind=heartbeat, target_thread_id, objective_fingerprint)`. Create only for
   zero matches, update one match, and fail closed on unreadable or multiple
   matches. Read back one active hourly heartbeat named exactly
   `OPL Flow Supervisor`; all registered Linear projects share it.
5. Each Supervisor run uses `list_threads` and a saved intake cursor to classify
   unseen or changed local tasks as `managed_objective`, `interactive_longline`,
   or `ephemeral_operation`. Development and delivery objectives are managed by
   default. A long-lived interactive operations or workbench task may be
   registered for visibility, but its root lifecycle remains user-owned. A
   short manual operation remains excluded unless the user explicitly asks to
   record it or it leaves a separate durable follow-up. Save the stable
   classification, lifecycle authority, and short reason in Dashboard internal
   metadata so later runs do not repeatedly reclassify it.
6. For every managed objective and registered interactive longline, use
   `read_thread` and the current owner surface to reconcile real execution,
   canonical Git/public/runtime state, blockers, remaining work, and the task
   title. When a root cause and reachable owner path are already known, route
   the owner-side repair or delivery bridge before requesting more proof; tests
   and callbacks are evidence, not the repair. Update Beads and Linear from
   those facts; never use a stale title, spinner, callback, checkpoint, PR, or
   local branch as proof of canonical completion. The Supervisor may report or
   route product-SSOT drift, but it never merges, publishes, deploys, or
   overwrites another owner's authority.
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
   after write; preserve hierarchy and the narrow field contract. When exactly
   one authorized human account is configured, assign every issue in each
   registered project to that account. With multiple accounts, require an
   explicit project mapping instead of guessing. Linear assignee is human
   accountability only; Beads/Dolt remains execution-owner truth. Do not use
   `bd linear sync`.
9. For every projected issue, use `mcp__codex_apps__linear_list_comments` and
   the registered project's saved comment-ID cursor. Use
   `send_message_to_thread` to send each later authorized user comment exactly
   once to its local Codex task with the comment ID as the idempotency key. If
   dispatch times out, record `timeout_unknown`, inspect the destination with
   `read_thread`, and allow one bounded retry only when that readback proves the
   comment absent. Track `comment_observed -> destination_delivery_confirmed ->
   owner_answer_read -> linear_reply_posted -> linear_reply_read_back ->
   cursor_advanced`; do not advance earlier. Begin every connector-posted answer
   with `【OPL Flow · Codex 自动回复】`, then name the source
   Codex task and whether answer provenance is owner readback, newly executed
   work, or another explicit authority. Treat this marker as non-user provenance
   even when Linear uses the same account as the human. Ignore Supervisor,
   Agent, Automation, and other non-user comments. `codex-paused` stops dispatch
   only; reconciliation and comment intake continue. A Cloud delegate is a
   conflict and fails closed.
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
- `list_threads` plus Dashboard metadata: every newly observed task has one
  stable intake classification; excluded operations/workbenches created no
  Bead or Linear issue, while managed objectives have one of each;
- `read_thread` plus owner authority readback: managed task facts, aggregate
  counts, and titles match actual execution and canonical state; no task was
  archived automatically;
- Linear `list_issues`/`get_issue`: one current issue per Bead after write;
  every registered project issue has the configured human assignee and the
  mismatch count is zero;
- Linear `list_comments` plus the destination task's `read_thread`: every
  authorized comment after the saved cursor has one confirmed delivery, one
  owner-answer readback, one marked Linear reply and reply readback; every
  skipped comment is marker-proven non-user, and the Beads cursor matches the
  last fully closed comment;
- `bd dolt pull` after push or explicit no-change: no remaining remote drift.

Repeating `start` must return the same Dashboard, Bead, and heartbeat IDs and
must create zero duplicates. Any missing, stale, unreadable, or ambiguous
readback leaves the action incomplete.

## Thread Intake And Titles

Automatic Ledger enrollment is purpose-based, not a blanket rule for every
conversation:

- `managed_objective`: finite development, delivery, release, research, or
  other project work with an owner and verifiable outcome. Software development
  belongs here by default and receives one Bead plus one Linear issue. Beads and
  authoritative owner readback manage its lifecycle; only an authoritative
  outcome with `remaining=[]` permits `SAFE_TO_ARCHIVE`.
- `interactive_longline`: a long-lived mail, persona, network, operations, or
  other interactive task the user intends to revisit over time. It may have one
  Bead and Linear issue for visibility, current status, comments, and concrete
  child work, but the Ledger never decides that the root task is complete. The
  only terminal signal is that the user archived the Codex task. A completed
  canary, bounded operation, canonical closeout, `remaining=[]`, idle turn, or
  stale title cannot produce `SAFE_TO_ARCHIVE`. Project its fresh thread state
  as `ACTIVE`, `NEEDS_ACTION`, `BLOCKED`, `MONITORING`, or `ON_DEMAND` until
  user archive. Use `ON_DEMAND` when there is no current work, external event,
  or user action; it maps to a Beads `pinned` issue and does not bind an
  execution thread.
- `ephemeral_operation`: short manual maintenance or interactive troubleshooting
  that should finish in its current task. Do not enroll it automatically. When
  the user explicitly asks to record it, the entry is record-only and the user
  archiving the Codex task is its lifecycle terminal. If it creates a distinct
  deadline, recurring duty, dependency, or development deliverable, enroll that
  durable follow-up separately as a `managed_objective`.

A durable responsibility is not by itself an `interactive_longline`. When a
bounded execution episode finishes and only a future due date or event trigger
remains, keep the durable Bead and Linear issue in `monitoring`, clear the live
`metadata.execution_thread`, and retain the completed thread only as
`metadata.last_execution_thread` provenance. Store a machine-readable due date
and short trigger set on the Bead. Mark the completed executor
`SAFE_TO_ARCHIVE`, and archive it only after fresh user approval. When a due
date or trigger fires, resume an unarchived bounded executor or create a new
one, bind it as the current `execution_thread`, and clear that binding again
after authoritative result readback. An archived `last_execution_thread` is
provenance only and must never be resumed; create a new bounded executor for
the next episode. Do not keep an idle task open merely to represent the
durable responsibility, and do not create a second Supervisor or heartbeat.

Use task titles as a human-readable projection only: `ACTIVE` for live work,
`NEEDS_ACTION` for a required user login/decision/authorization, `BLOCKED` for
an external dependency, `MONITORING` for a persistent workbench or supervisor,
and `SAFE_TO_ARCHIVE` only after authoritative terminal readback. Updating a
title never archives the task and never changes product SSOT. For
`interactive_longline` and explicitly recorded `ephemeral_operation`, never set
`SAFE_TO_ARCHIVE`; fresh user archive is the terminal authority, and any live
turn must repair a stale terminal title back to its actual execution state.

## Linear Field Authority

Linear to Beads: human intent, priority, due, explicit opt-out `codex-paused`,
and cancel.

Beads to Linear: execution state, blocker, result.

Beads lifecycle and visible execution activity are separate. Keep the durable
lifecycle in the native Beads status and store exactly one current
`metadata.execution_mode`: `active`, `waiting_user`, `waiting_external`,
`backlog`, `monitoring`, `on_demand`, or `aggregate`. Linear displays `Needs Action` when the owner's
login, decision, or authorization is the next step; it displays `Blocked` when
an external event or dependency prevents progress. Neither state keeps an Agent
allocated. `Monitoring` also allocates no Agent unless a bounded execution
episode is currently bound. When Linear is read back, both preserve a Bead
already in `blocked`; otherwise they keep `in_progress`. `Monitoring`
normalizes to `in_progress`; `on_demand` requires Beads `pinned`, Linear `On Demand`,
a null `execution_thread`, `interactive_longline`, and user-intent/explicit-trigger
dispatch only. Planned finite development with no allocated executor uses
`backlog`, Beads `deferred`, and Linear `Backlog`; it returns to execution when
capacity or its declared dependency releases it. Only genuinely unplanned work
displays `Todo`.

Aggregate issues roll up descendants: an active descendant displays `In
Progress`; otherwise owner action takes precedence over external blocking,
which takes precedence over monitoring. No unresolved descendants displays
`Done`. Unknown or ambiguous execution mode fails closed without changing
Linear.

Project only identity, title, hierarchy, status, priority, due, pause intent,
execution mode, display status, cancel intent, short blocker/result, and links.
Exclude credentials, local paths, logs, full notes, metadata, and checkpoints.

Every issue in a registered project is managed by local Codex by default.
`codex-paused` is the sole explicit dispatch pause and blocks dispatch only;
Linear reconciliation and authorized user comment intake continue so resumption
does not lose human intent.

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
