# Ledger Start

Use this reference only for explicit `$opl-flow start`. `OPL Ledger` is the
owner Instance's complete human work ledger, not the Supervisor or an OPL-source
project list. Setup, update, and install never run this route.

## Idempotent Onboarding

1. Resolve the saved Codex project, local environment, unique private Instance,
   and objective fingerprint. Ask only on material ambiguity.
2. Use `list_threads` to match `(project_id, objective_fingerprint)`. Reuse one
   Dashboard, use `create_thread` only for zero matches, and fail closed on
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
5. Each Supervisor run reads ready, in-progress, overdue, and live local tasks,
   acts on current user intent, and records claim/checkpoint/blocker/remaining
   in Beads. Before remote dispatch, read the Bead's single
   `metadata.opl_execution_requirements` object. If absent, keep execution in
   the current Codex session. If present, validate it against
   `contracts/execution-requirements.schema.json`, then use `$opl-fleet` for
   plan, fresh admission, lease, adapter execution, result readback, and
   release. Record only the dispatch ID and short outcome in the Bead; never
   store lease nonces, private routes, command output, or credentials.
6. Reconcile every user-ledger Bead to exactly one Linear issue through
   `mcp__codex_apps__linear_list_issues`, `mcp__codex_apps__linear_get_issue`,
   and `mcp__codex_apps__linear_save_issue`. Read before write and read back
   after write; preserve hierarchy and the narrow field contract. Do not use
   `bd linear sync`.
7. For every projected issue, use `mcp__codex_apps__linear_list_comments` and
   the registered project's saved comment-ID cursor. Use
   `send_message_to_thread` to send each later authorized user comment exactly
   once to its local Codex task with the comment ID as the idempotency key.
   Advance the cursor only after delivery or a recorded non-user ignore. Ignore
   Supervisor, Agent, Automation, and other non-user comments. `codex-paused`
   stops dispatch only; reconciliation and comment intake continue. A Cloud
   delegate is a conflict and fails closed.
8. Keep Ambient Ops inside this Ledger as an OPL Fleet observability extension;
   it never creates another Supervisor or heartbeat.
9. After one coherent mutation, run `bd dolt push`, then pull and read the
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
- Linear `list_issues`/`get_issue`: one current issue per Bead after write;
- Linear `list_comments` plus the destination task's `read_thread`: every
  authorized comment after the saved cursor is delivered once, every skipped
  comment is non-user, and the Beads cursor matches the last handled comment;
- `bd dolt pull` after push or explicit no-change: no remaining remote drift.

Repeating `start` must return the same Dashboard, Bead, and heartbeat IDs and
must create zero duplicates. Any missing, stale, unreadable, or ambiguous
readback leaves the action incomplete.

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
allocated. When Linear is read back, both preserve a Bead already in `blocked`;
otherwise they keep `in_progress`. `Monitoring` normalizes to `in_progress`;
only genuinely unstarted work displays `Todo`.

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
