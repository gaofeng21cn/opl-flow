---
name: dsh-code-review
description: Use for evidence-backed code review of a pull request, branch, commit range, or worktree; verifies the live base and complete task-owned change, traces changed interfaces and shipped entry paths, and reports actionable correctness findings before style.
---

# Review A Code Change

Use `$develop-and-deliver` as the delivery owner. This Skill is review guidance,
not a complete checklist and not authorization to edit, push, merge, or publish.

## Establish The Live Change

Read repository instructions, verify and fetch the actual base, and resolve the
exact head, PR, commit range, or worktree state. Inspect committed, staged,
unstaged, and relevant untracked paths that belong to the requested change.
Re-establish the scope after a retarget, base merge, or history rewrite.

Read enough surrounding code and current contracts to understand intent. Treat
design records, tests, and documentation as evidence, not automatic veto or
proof. Prioritize reproducible correctness, security, data integrity, lifecycle,
compatibility, and required behavior over style or speculative improvement.

## Trace The Real Behavior

- Follow both sides of every changed interface and every production consumer.
- Check ownership, state authority, errors, cancellation, concurrency, cleanup,
  disposal, borrowed versus retained values, and cache invalidation where the
  change can affect them.
- Trace enforcement to the final operation, including alternate callers that
  can bypass schemas, prompts, wrappers, hooks, or listener ordering.
- Exercise the shipped loader, command, worker, subprocess, bridge, generated
  artifact, or wire path when a hand-mounted unit path would miss the defect.
- Check tiny, boundary, negative, oversized, and multibyte cases when bounds or
  guards change.
- Require assertions that fail for the claimed regression and observe external
  state, events, logs, errors, or cleanup rather than restating implementation.
- Review changed docs, comments, prompts, diagnostics, and visible strings with
  `$dsh-prose-standard`; passing mechanical gates do not prove semantic quality.

Challenge new abstractions, public operations, state machines, compatibility
paths, defensive copies, and defaults that lack a current caller, owner,
contract, observed failure, or reachable risk.

## Report Findings

Lead with findings ordered by severity. For each, name the tightest file and
line, triggering path, impact, and concrete evidence. Separate defects from
suggestions and omit style findings already enforced by a passing deterministic
gate. If there are no findings, say so and name residual untested surfaces.
