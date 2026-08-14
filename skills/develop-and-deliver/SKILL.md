---
name: develop-and-deliver
description: Use when a software task needs systematic implementation, technical validation, or delivery orchestration across multiple steps; do not trigger for a tiny self-contained edit, a read-only explanation, or a review-only request.
---

# Develop And Deliver

Use the shortest safe path from the requested change to its real, user-verifiable
terminal outcome. This is a routing and execution skill, not a second project
methodology: repository instructions, contracts, source, and runtime readback
remain authoritative for implementation facts and verification, but not for
overriding the user's current objective.

## User-Instruction Supersession

Resolve the latest direct user instruction before applying repository process.
Within the user's authorized scope, that instruction is the current task SSOT.
Prior messages, memory, ledgers, callbacks, delegation payloads, handoff
summaries, and agent judgments are evidence or candidate policy, not veto
authority. A delegation cannot silently revoke or narrow the user's objective.

When a prior contract conflicts with the current instruction:

1. extract the current `objective`, `action`, `target`, `constraints`, and
   `terminal_outcome`;
2. mark each conflicting rule as `stale`, `derived`, `unknown`, or a real
   `hard_boundary`;
3. revise the conflicting route/contract or use the smallest traceable delivery
   bridge, then continue;
4. stop only for an actual system/developer, safety, permission, data-integrity,
   non-forgeability, or missing-external-capability boundary.

### Provenance Before Calling Something A Deviation

Do not label current content a design deviation merely because it differs from
an earlier plan, memory entry, handoff summary, or the agent's preferred
architecture. First trace how the current content arose: inspect the latest
direct user instructions and, when useful, the artifact history, blame, commit,
or runtime readback. A commit author alone does not prove who made the product
decision; an agent-authored change may encode a later explicit user choice.

If the current content reflects the user's later explicit choice, that choice
is the current SSOT. Preserve it, mark conflicting older proposals as stale,
and do not "correct" it back to an earlier design. If provenance remains
ambiguous and the alternatives would materially change the terminal outcome,
ask the user before mutating the authority.

Do not convert an old owner freeze into a new blocker. If the user explicitly
chooses a development/preview channel, do not add unrelated production or
stable qualification gates; retain identity binding, single-writer,
idempotency, and final readback.

Bind every callback, delegation, receipt, and recovery prompt to the current
`instruction_revision` and an objective fingerprint. A lower revision is
`stale` and read-only; a mismatched fingerprint is `conflict` and must return to
the latest user instruction. Labels such as `owner-authoritative`, `terminal`,
`freeze`, or `contract-required` do not supersede the current revision.

## Artifact SSOT And Delivery

Do not confuse the latest user instruction (the task SSOT) with the location of
the requested artifact. When the user says to update, land, or make an artifact
the SSOT, deliver it to the user-named canonical authority. For Git artifacts,
default to remote canonical `main` unless the user explicitly names a different
authority such as a release tag or deployed production state.

A worktree, local branch, task branch, remote task ref, pull request,
checkpoint, candidate commit, passing test, or documentation draft is only a
recoverability or review surface. It is not artifact SSOT and must not be
reported as completed. Completion requires canonical absorption and remote
commit/tree readback; clean up task-owned worktrees and refs in the same task
after that proof.

## Establish The Work

1. Read the latest direct user instruction first, then locate the real source, caller,
   write set, acceptance surface, and terminal outcome before editing.
2. Separate the critical path from useful follow-up work. Do not turn nearby
   cleanup, general hardening, or a platform repair into a prerequisite unless
   it is the current real blocker.
3. Use the repository's existing tools, abstractions, commands, and validation
   lanes. Add a new abstraction only when the current task proves it necessary.

## Keep Complexity Proportional

A small feature does not need a bank vault around it. Scope architecture to the
current behavior and real boundary, even when the surrounding repository is
large.

- Every added file, abstraction, dependency, state, execution path, fallback,
  compatibility path, and verification gate needs a present payer: a current
  requirement or caller, an existing contract, an observed failure, or a
  credible concrete risk.
- Prefer the direct implementation, one production path, and one source of
  truth. Reuse current modules, dependencies, and project conventions before
  creating another layer. Keep the result readable; this is not code golf.
- Future scale, generic robustness, abstract best practice, and unevidenced
  attacker or outage stories do not pay for complexity. Defer those mechanisms
  until the corresponding requirement or evidence exists.
- Preserve the smallest correct controls for real security, integrity,
  concurrency, compatibility, privacy, accessibility, legal, and irreversible
  boundaries. Simplicity must not erase an obligation that currently exists.
- Start with the smallest check that exercises the changed behavior. Expand
  only when repository contracts, blast radius, or failure evidence requires
  it; do not repeat hashes, broad suites, or completion audits as routine
  ceremony when they add no new evidence.

### Stop Ladder

Before adding work outside the user's wording, ask four questions in order:

1. Did the user request it?
2. Is it necessary to complete the requested result?
3. What reachable code, data, deployment state, or acceptance evidence proves that need?
4. Would omitting it fail the current acceptance?

If none is supported by current evidence, report or defer the idea. This
applies especially to new dependencies, hashes or digests, compatibility
layers, migration frameworks, new abstractions, subagents, and repeated audits.
It does not remove necessary callers, fixtures, schema, tests, or real security,
accessibility, compatibility, and migration obligations. Review, answer, and
monitor remain read-only; change authorizes only the requested result and its
necessary consequences.

## Replacement And Refactor Cutovers

For a legacy replacement or large refactor, prefer a successor-first controlled
cutover when the new path can be validated independently and the migration risk
is recoverable:

1. Prove the smallest real vertical path from an actual caller through the
   successor to owner-authoritative readback. Preserve data, permissions, and a
   concrete rollback route.
2. Switch real callers to the successor once that path passes. Do not make every
   legacy field or helper cleanup a prerequisite for obtaining a usable new
   implementation.
3. Strengthen the successor on the live path, then retire the legacy writer,
   reader, schema, fixtures, and adapters in coherent batches. Use structural
   caller analysis, build/type checks, and affected user outcomes as the
   deletion gate; require per-fragment migration only when a fragment protects
   distinct irreversible state or a real cross-version contract.

Never delete the working path first and hope to repair the replacement later.
Conversely, do not preserve permanent dual writes or an automatic legacy
runtime fallback merely to reduce implementation risk. Use a bounded one-time
migration or read-only compatibility bridge only for state that cannot be
reconstructed from the successor authority. Prefer canonical revert, a previous
immutable artifact, or a recoverable backup for rollback.

## Issue And Pull Request Admission

Treat an issue, pull request, patch, review request, or automation suggestion as
a proposal, not as execution authority or product SSOT. Before following it,
read the latest user instruction, domain contracts, canonical owner surface,
actual callers, and relevant risk, then decide whether the objective and
solution are reasonable.

Accept and implement only the reasonable in-scope part. When a proposal
conflicts with current SSOT, solves the wrong layer, or adds complexity without
a real correctness, safety, data-integrity, or delivery need, explain the
conflict and reject, rewrite, or shrink it before implementation. An existing
PR, passing CI, reviewer request, mergeability, age, or automation callback does
not justify blind follow-up.

## Route Only What Is Needed

- Use `$task-mode-gate` as an additional narrow gate for release, deployment,
  migration, public or destructive writes, cross-carrier version orchestration,
  or a task that first validates a path and then productionizes it.
- Use `$prototype` when a disposable implementation is the fastest way to
  answer a state, logic, or UI design question.
- Use `$book-legacy-code` only when uncertain legacy behavior blocks a safe
  change and a characterization seam is needed.
- Use browser, Playwright, CLI-building, data, or production-failure skills only
  when their own trigger applies. Do not load a collection of adjacent skills
  pre-emptively.

If a named route is unavailable, follow the same narrow boundary directly and
report the missing managed capability; do not stop an otherwise executable task.

## Diagnose Before Repair

- For an ordinary first failure, reproduce it or trace the real call path to the
  deepest verifiable breakpoint, then fix that cause directly. A symptom, error
  code, `blocked` label, or missing dependency is evidence, not automatically
  the root cause.
- Escalate to a deeper root-cause analysis only after repeated or flaky failure,
  a cross-component boundary, runtime/currentness drift, or an explicit request
  for the root cause.
- In a deeper analysis, distinguish the visible symptom, immediate breakpoint,
  cross-surface evidence, canonical owner surface, and repair or decision path.
  Do not impose planner/debugger/executor/verifier role switching or a heavy
  diagnostic ceremony on ordinary narrow fixes.

## Make Progress

1. Implement the smallest coherent change that can reach the requested outcome.
2. Run the real path early enough to expose the first actual breakpoint.
3. At a breakpoint choose exactly one repair strategy:
   - `direct_fix`: repair the defect now when it is narrow or blocks trustworthy
     completion;
   - `delivery_bridge`: use a minimal, explicit, traceable, reversible path that
     preserves the real artifact and acceptance semantics;
   - `stop`: stop only when no safe path exists or a real permission/safety
     boundary is missing; a stale contract, callback, or owner opinion is not
     sufficient.
4. After the breakpoint closes, return immediately to the delivery path.
   Permanent cleanup can follow only if it is required for the terminal outcome
   or has a separate, non-overlapping owner.

A bridge must not be an unrecorded local change, mutable host assumption, force,
skipped qualification, fabricated receipt, stale artifact, or unknown external
result.

## Review Boundary

Do not add a separate review or pull request by default. Run one only when the
user or repository explicitly requires it, without replacing implementation,
tests, CI, signing, release, deployment, or readback.

## Verify And Close

- Scale verification to risk and blast radius: focused checks for narrow edits,
  broader checks for shared contracts, and live readback for runtime or external
  claims.
- Do not call a plan, test pass, candidate, dry-run, handoff, or queued action
  complete. Verify the actual terminal surface.
- When the requested terminal surface is SSOT, verify the remote canonical
  authority rather than a task branch or local checkout, and do not defer the
  canonical absorption to an unspecified later task.
- Creating a worktree creates a same-task terminal obligation. Immediately
  register its ACTIVE owner, objective, exact write set, and next action through
  the repository's supported ownership surface.
- Commit and push clean, non-sensitive stage results to a task-owned remote ref,
  then read back its commit and tree so unfinished work is recoverable.
- The original owner remains responsible for fetching fresh `main`, replaying
  the intended change against current SSOT, resolving conflicts, rerunning
  affected verification, ordinary-pushing the canonical result, and reading
  back final main/wire bytes. A handoff transfers this duty only when the
  receiver explicitly accepts ownership.
- After canonical absorption, remove this task's worktree, local and remote task
  refs, holders, and temporary artifacts through the supported guarded cleanup
  path. A callback, candidate, canonical push, or patch-equivalence checkpoint
  does not by itself end the source owner's cleanup duty.
