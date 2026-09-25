# Grok Build Handoff Contract

Write the handoff as current execution authority, not as a transcript. Keep exact facts and remove superseded exploration.

Include these fields when they affect the task:

## Objective And Terminal Outcome

- State the user-visible result and what counts as complete.
- Separate implementation completion from commit, canonical integration, deployment, or publication.

## Authority And Ownership

- Name the repository authority and the only writable checkout/worktree.
- Record branch, baseline commit/tree, current dirty state, and any concurrent owner.
- State that Grok is the sole implementation writer and Codex will independently verify.

## Write Set And Boundaries

- List the exact files or owned surfaces Grok may edit.
- List forbidden repositories, worktrees, devices, services, credentials, destructive Git actions, and external mutations.
- State whether commit, ordinary push, canonical integration, deployment, or cleanup is authorized. Never infer these from permission mode.

## Settled Evidence

- Give the real caller/path, deepest verified breakpoint, relevant contracts, and facts that must not be rediscovered.
- Identify disproved approaches and stale assumptions only when they would otherwise waste work or cause a regression.
- Keep secrets and private runtime data out of the handoff.

## Required Implementation

- Describe the smallest owner-side behavior change and invariants that must remain true.
- Prefer behavior and contracts over prescribing incidental code shape.
- Require the first tool call to read `pwd`, Git status/branch/HEAD, and the named source surfaces.
- Say explicitly that Grok must not claim a change without a non-empty diff or a new exact commit.

## Verification And Report

- Name focused tests, aggregate gates, browser/runtime checks, and unavailable-tool behavior.
- Require final `git status`, diff stat/check, exact commit/tree when applicable, tests, remaining gaps, and external-mutation count.
- Require Grok to report an unavailable or repeatedly failing tool as a blocker and never replace missing tool evidence with a completion claim.
- If the task depends on another owner, define the fresh readback and resume condition; do not authorize polling to become a second writer.

Use task-specific deny rules at process launch for high-impact forbidden commands. The prose handoff and CLI denies are complementary: the handoff defines authority and intent; denies provide a deterministic backstop.
