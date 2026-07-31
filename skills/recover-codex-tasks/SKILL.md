---
name: recover-codex-tasks
description: Use when recovering missing, interrupted, hidden, or unreadable Codex tasks and side conversations after an app restart or thread bug; when a user says a Codex task, sidebar conversation, delegated side task, sub-agent, or in-progress turn disappeared; when a known thread ID returns `No Codex thread found`; or when work must be reconstructed from Codex thread tools, `state_5.sqlite`, rollout JSONL, spawn graphs, Git worktrees, and receipts without replaying a live shared mutation.
---

# Recover Codex Tasks

Recover the user's objective and a usable conversation entry, not merely a
historical transcript. Preserve current Git/runtime ownership while rebuilding
the missing task from fresh evidence.

## Non-Negotiable Boundaries

- Treat Codex thread APIs as the UI/runtime authority and SQLite/rollout files
  as read-only evidence.
- Never edit `state_5.sqlite`, move rollout files to simulate recovery, or
  invent a thread ID.
- Do not treat a thread title, task branch, checkpoint, test pass, or archived
  rollout as current execution truth.
- Do not create a second writer for the same shared checkout, canonical mutation,
  release, deployment, VM, or runtime operation. An independent Git worktree and
  branch may continue in parallel, including with an overlapping write set;
  resolve conflicts at fresh canonical integration.
- Do not archive an old task merely because a continuation was created.
- Preserve unrelated dirty worktrees, active processes, credentials, sessions,
  caches, and native app state.

## Recovery Workflow

### 1. Freeze New Mutations

Start read-only. Record the user's requested objective, known thread IDs,
project/repository, approximate time, visible title, related owners, and the
last remembered checkpoint.

If the missing task controlled a shared checkout, release, VM, install, or other
external state, identify the current operation owner before sending follow-ups
or creating a successor. A separate worktree implementation does not need to
wait for an unrelated writer; record the overlap and integrate it later.

### 2. Probe the App Task Surface

Search for and use the Codex task tools first:

1. `list_threads` to inspect visible and pinned tasks.
2. `read_thread` for every known candidate ID.
3. `wait_threads` with `timeoutMs: 0` for a fresh status snapshot when needed.

Classify the result:

| Evidence | Classification | Default action |
|---|---|---|
| Task readable and current turn intact | `readable` | Continue the same task |
| Task readable, latest turn interrupted/system error | `interrupted` | Send one recovery prompt to the same task |
| Task row/history exists but app returns `No Codex thread found` | `unreadable` | Reconstruct, then create a continuation if authorized |
| Parent rollout contains `spawn_agent`, but no stable child ID | `ephemeral` | Reconstruct the side task by task name and callbacks |
| Writer task is unreachable and work remains | `writer_unreachable` | Establish fresh authority transfer before a successor writes |

Do not repeatedly wake an unreadable task. One failed `read_thread` probe plus
matching read-only evidence is sufficient to switch to reconstruction.

### 3. Inspect SQLite and Rollouts Read-Only

Run the bundled inspector before ad hoc SQL:

```bash
python3 <recover-codex-tasks-skill-root>/scripts/inspect_codex_recovery.py \
  inspect --thread-id <thread-id> --term <keyword>
```

Search task metadata when the ID is unknown:

```bash
python3 <recover-codex-tasks-skill-root>/scripts/inspect_codex_recovery.py \
  search <keyword-1> <keyword-2> --limit 30
```

Use [evidence-and-prompts.md](references/evidence-and-prompts.md) only when the
inspector does not expose enough detail or a continuation prompt is needed.

Distinguish:

- persistent child tasks in `thread_spawn_edges`;
- collaboration side tasks recorded only as `spawn_agent` task names;
- user-visible tasks created later with `create_thread`;
- encrypted spawn prompts, which may be unrecoverable even when task names and
  final callbacks remain visible.

Extract only messages, task calls, task IDs, status callbacks, and concise final
text. Avoid broad scans of attachment payloads, images, base64, or full tool
outputs.

### 4. Reconcile the Real Work

Before deciding what to resume, refresh:

- current task status and unique objective owner;
- canonical remote refs and exact write sets;
- registered worktrees, dirty state, holders, locks, and remote checkpoints;
- active workflow runs, VM leases, installs, publications, or runtime receipts
  when relevant.

Historical thread recovery never authorizes replaying an old mutation. Unknown
external results require bounded read-only reconciliation.

### 5. Choose the Smallest Valid Recovery

Prefer these routes in order:

1. **Resume original task**: send a concise prompt containing the objective,
   fresh authority, last checkpoint, first remaining action, and forbidden
   duplicate mutations.
2. **Create a read-only continuation**: use when a side discussion/audit was
   ephemeral or unreadable while the original writer still exists.
3. **Create a writer successor**: use only when the writer itself is
   unreachable, remaining work is real, and authority transfer plus exact
   write set have been established.
4. **Report historical-only**: use when the objective is already fully covered
   by canonical/runtime authority and no independent obligation remains.

For user-visible continuation tasks:

- call `list_projects` first;
- use the saved project directly for a read-only discussion/review task;
- use a worktree for a new Git writer;
- inject the reconstructed context and explicit ownership boundary;
- set an `ACTIVE｜<surface>｜<objective>` title and pin it;
- wait for fresh progress and verify it is doing work, not only carrying a
  title;
- emit the created-task directive only after creation succeeds.

### 6. Close the Recovery Operation

Report:

- whether the original task was directly recoverable;
- the evidence source used: task API, SQLite row, spawn graph, rollout, Git, or
  receipt;
- original and continuation IDs, if available;
- current unique owner and exact mutation boundary;
- what progress survived and what was lost;
- the continuation's first live action;
- mutations explicitly not performed.

Recovery is complete only when the user has a readable task entry and the
objective has one live owner with a concrete next action. The product objective
may remain `ACTIVE`.

## Failure Rules

- If SQLite is locked or unavailable, use task tools and rollout files; do not
  copy or repair the database.
- If rollout content is encrypted, use task names, timestamps, callbacks, Git
  state, and receipts; label unrecoverable wording as unknown.
- If several candidates are plausible, do not merge their responsibilities.
  Create a continuation from only the common proven scope and list the
  unresolved identity question.
- If a new task starts writing the same shared checkout or external operation,
  immediately stop that operation and either convert it to read-only
  coordination or establish an explicit owner transfer. Do not stop an
  independent worktree merely because its write set overlaps another branch.
