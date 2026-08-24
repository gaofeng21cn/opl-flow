---
name: software-development
description: "Use for non-trivial software work: implementation and delivery, code review, architecture or simplification, developer documentation, prototypes, CI or pull-request maintenance, production reliability, or release and deployment. Excludes tiny edits, ordinary explanations, OPL Flow product operations, and Codex task management."
---

# Software Development

Route non-trivial software work to one focused guide. Keep ordinary reasoning,
small edits, and repository-local decisions model-native. Repository
instructions, contracts, source, callers, tests, and runtime readback remain
authoritative.

## Choose One Mode

Load only the reference named by the selected mode and any explicitly required
sub-guide.

| Mode | Use when | Load |
| --- | --- | --- |
| `delivery` | Implement, refactor, validate, or deliver a software change. | `references/delivery/guide.md` |
| `review` | Review a PR, branch, commit range, or worktree without editing by default. | `references/review.md` |
| `architecture` | Map, improve, simplify, or pressure-test a codebase or design. | `references/architecture/guide.md` |
| `systems` | Distributed-data correctness or production failure semantics materially affect the change. | One file under `references/systems/` |
| `docs` | Govern developer documentation, decision records, sites, prose, or a bilingual pair. | `references/docs/governance.md`, then one focused docs reference |
| `github` | Patrol GitHub state or land an official pull-request stack. | One guide under `references/github/` |
| `prototype` | Build a disposable logic or UI experiment to answer a concrete question. | `references/prototype/guide.md` |
| `browser-evidence` | Record and verify a real browser interaction artifact. | `references/browser-evidence/guide.md` |

Within `delivery`, load `legacy-change.md`, `pre-push.md`, or
`production-change.md` only when that exact boundary is present. Within
`architecture`, load only the requested map, improvement, simplification,
grilling, or named lens reference.

## Boundaries

- Use `$manage-codex-tasks` when the work requires multiple Codex tasks,
  worktree integration, task recovery, or execution-owner transfer.
- Use `$opl-flow` for OPL Flow Profile, Package, Ledger, or Fleet operations.
- Use platform or domain Skills for their actual implementation domain; this
  router owns the development path, not every technology manual.
- A release, deployment, migration, public write, or destructive mutation loads
  `references/delivery/production-change.md` before the first real mutation.
- Do not load neighboring guides pre-emptively or turn this router into a
  planner/executor role system.

## Finish

Verify in proportion to the changed behavior and report the real requested
terminal surface. A plan, test pass, local commit, task branch, or queued action
is evidence only for its own layer.
