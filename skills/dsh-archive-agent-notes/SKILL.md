---
name: dsh-archive-agent-notes
description: Use when auditing, superseding, retaining, archiving, restoring, or deleting repository decision records; preserves future decision value without imposing DeepSeek Harness Agent Notes, fixed triplets, or a second archive ledger.
---

# Archive Decision Records

This is the OPL adaptation of DeepSeek Harness decision-note retention. Use
`$opl-doc` as the semantic owner and the target repository's existing ADR, RFC,
Agent Note, postmortem, or history lifecycle as the storage authority.

## Establish The Record Owner

Read the repository instructions and the applicable decision-record rules.
Use current source, configuration, contracts, callers, tests, current docs,
newer decisions, and inbound references to identify what owns the decision now.
Dates, filenames, word counts, and lifecycle labels are discovery hints only.

## Classify By Future Decision Value

- Keep a shipped record active when its rationale, alternatives, negative
  guarantees, ownership boundary, durable or wire semantics, security rule, or
  reintroduction condition can still guide a plausible future change.
- Archive or demote completed history only when current authority owns the
  behavior and the remaining record is unlikely to affect a future decision.
- Never archive a live proposal merely because it is old. Keep it active or
  reject it honestly through the repository's lifecycle.
- Keep a rejected record only while the losing idea remains a plausible mistake
  and the record explains why it loses. Otherwise delete it when authorized.

Do not archive toward a quota or because a record is long. Do not create an
English/translated/sidecar triplet, frozen manifest, hash ledger, or archive
directory unless the target repository already owns that contract.

## Resolve Supersession

For every overlapping record, distinguish full from partial supersession. Full
supersession requires the current owner to retain every unique rationale,
alternative, consequence, verification obligation, compatibility fact, and
reintroduction condition that still matters. Keep partial supersessions active
and cross-linked. Repair or remove inbound links before deleting a record.

Apply the target repository's own archive mechanics exactly. Treat frozen
history as read-only only when that repository already declares it frozen.

## Verify And Report

Run the repository's focused documentation, link, format, or archive checks and
`git diff --check`. Report records kept, archived or demoted, rejected, deleted,
and any genuinely borderline case with the future value that determined the
outcome. Do not claim runtime or product readiness from documentation cleanup.
