---
name: recover-codex-tasks
description: Use when a Codex task is missing, interrupted, hidden, or unreadable after a restart or thread failure; recover it through native Codex task/thread tools while preserving current ownership.
---

# Recover Codex Tasks

Recover the user's objective and a readable task entry. Treat native Codex
task/thread tools as the authority and start read-only.

## Workflow

1. Record the requested objective, known task IDs, repository, last checkpoint,
   and any shared checkout or external operation it owned.
2. Use `list_threads` to find candidates, `read_thread` to inspect each exact
   task, and `wait_threads` for a fresh status snapshot.
3. If the task is readable and still running, wait. If its latest turn was
   interrupted, use `send_message_to_thread` once with the objective, surviving
   checkpoint, first remaining action, and current mutation boundary.
4. If the task is unreadable, report that exact native readback. Create or fork
   a successor only when the user explicitly requests a new task or an already
   authorized Beads owner-migration objective requires a replacement executor.
   Before a writer successor starts, fresh-read Git/runtime ownership and
   establish the Beads execution-owner transfer.
5. Read back the resumed or new task. Recovery is complete only when it is
   readable, has one live owner, and has begun a concrete next action.

## Boundaries

- Do not inspect or modify private Codex databases or rollout files while the
  native task/thread surface is available.
- Do not infer live status from a title, branch, checkpoint, test, or old
  transcript.
- Do not create a duplicate writer for a shared checkout, canonical mutation,
  release, deployment, install, VM, database, or runtime operation.
- When a Bead has `owner_mutation_frozen=true`, follow its migration receipt;
  do not resume the old task or infer an ownerless gap from native task state.
- Do not archive the old task merely because a continuation exists.
- If native task tools are unavailable, use only current Git/runtime evidence
  and user-provided context; label the missing task history as unknown.

Report the original and successor IDs, current owner and mutation boundary,
surviving progress, first live action, and mutations not performed.
