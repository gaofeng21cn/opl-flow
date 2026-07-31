# Evidence And Prompt Reference

Use this reference when the bundled inspector is insufficient or when creating
a continuation task.

## Evidence Order

1. Codex app task tools: visibility, readability, live status, follow-up.
2. `state_5.sqlite` in read-only mode: task metadata and persistent spawn edges.
3. Rollout JSONL: ephemeral `spawn_agent` names, callbacks, completed messages.
4. Git/runtime evidence: current owner, write set, worktree, checkpoint,
   canonical authority, external mutation readback.

Later evidence does not override the task API's ability to open a task. It only
explains what must be reconstructed.

## SQLite Surfaces

Default database:

```text
~/.codex/state_5.sqlite
```

Relevant tables:

```text
threads
  id, rollout_path, created_at, updated_at, cwd, title, archived,
  first_user_message, preview, agent_nickname, agent_role, thread_source

thread_spawn_edges
  parent_thread_id, child_thread_id, status
```

When manual SQL is unavoidable, always use:

```bash
sqlite3 -readonly ~/.codex/state_5.sqlite
```

Never run `UPDATE`, `INSERT`, `DELETE`, schema changes, vacuum, or journal
recovery against the live database.

## Rollout Filters

Inspect function calls without emitting large outputs:

```bash
jq -rc '
  select(.type=="response_item" and .payload.type=="function_call")
  | [.payload.name,.payload.call_id,.payload.arguments] | @tsv
' <rollout.jsonl>
```

List ephemeral side task names:

```bash
jq -rc '
  select(.type=="response_item"
    and .payload.type=="function_call"
    and .payload.name=="spawn_agent")
  | (.payload.arguments|fromjson)
  | [.task_name,.fork_turns] | @tsv
' <rollout.jsonl>
```

Do not grep raw function outputs across all rollouts unless targeted filters
fail; nested browser/image/tool data can create huge false matches.

## Resume Prompt

Use for a readable task whose turn was interrupted:

```text
【CODEX RESTART RECOVERY｜RESUME UNIQUE OWNER】
The previous turn was interrupted by a Codex restart. Continue the same
objective as the unique owner. First fresh-read current task state, canonical
authority, exact write set, worktree/checkpoint parity, and external mutation
status. Do not replay unknown mutations. Resume from <checkpoint>; the first
remaining action is <action>. Keep <forbidden surfaces> at mutation0.
```

## Read-Only Continuation Prompt

Use when an ephemeral discussion/audit disappeared but a writer survives:

```text
This is a user-visible continuation of an ephemeral side task lost after a
Codex restart. Reconstruct from fresh task readback, SQLite/rollout evidence,
and current authority. The original writer remains <thread-id>; this task is a
read-only discussion/audit surface and must not mutate the original shared
surface. If implementation is still needed, use a separately registered
worktree with an explicit write set.

Objective: <objective>
Known evidence: <task IDs, checkpoint, write set>
First action: <fresh read-only action>
Terminal for this recovery: a verified owner map, concrete next action, and a
readable continuation entry.
```

## Writer Successor Prompt

Use only after authority transfer is proven:

```text
This task is the fresh successor for <objective>. The predecessor <thread-id>
is unreadable/unreachable and its write authority is released as of <evidence>.
You are the writer for the independent worktree and exact write set <paths>.
The predecessor's shared checkout or external mutation remains untouched. Start
from fresh canonical <ref>, reconcile checkpoint <ref/SHA>, and do not repeat any unknown
external mutation. Complete semantic replay, verification, ordinary canonical
push, wire readback, and task-owned cleanup.
```

## Recovery Verification

After creating or resuming a task, confirm:

- the task is readable;
- its latest turn is `inProgress` or it produced a completed first checkpoint;
- its first commentary reflects the injected objective;
- it names the correct owner/write boundary;
- no duplicate shared checkout mutation, workflow run, VM, or external mutation
  appeared. Independent worktrees are valid when each has its own receipt and
  recovery point.
