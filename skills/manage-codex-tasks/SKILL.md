---
name: manage-codex-tasks
description: "Use only to coordinate multiple native Codex tasks, or to recover, resume, integrate, hand off, or transfer ownership of missing or interrupted work across tasks, worktrees, repositories, or machines. Excludes ordinary single-task execution, visible-task navigation, and general history."
---

# Manage Codex Tasks

Manage the native Codex task control plane without creating duplicate writers
or treating task state as product completion. Use exactly one mode.

## Choose One Mode

| Mode | Use when | Load |
| --- | --- | --- |
| `coordinate` | Assign owners and write sets across multiple tasks, repositories, worktrees, agents, or machines. | `references/coordinate.md` |
| `integrate` | Absorb prepared work against fresh canonical state and close owned temporary surfaces. | `references/coordinate.md` |
| `recover` | A Codex task is missing, interrupted, hidden, or unreadable after a restart or failure. | `references/recover.md` |
| `migrate-owner` | Move a durable task owner to a native, user-visible Codex App task on another machine. | `references/migrate-owner.md` |
| `archive-readiness` | Determine whether completed tasks have canonical absorption, empty remaining work, and no lifecycle obligation. | `references/coordinate.md` |

Native task tools are the task/thread authority. Git owns source currentness and
recoverable checkpoints; product/runtime owners own their terminal state. A
title, spinner, callback, test, branch, or task receipt does not prove any of
those other surfaces.

Use `$opl-flow fleet` only when cross-machine admission, workspace currentness,
or protected capacity is actually required. Never archive a task without fresh
user approval.
