---
name: dsh-find-simplifications
description: Use when auditing a codebase for evidence-backed simplification candidates such as unused public surfaces, duplicate state, speculative generality, shallow packages, or hand-rolled infrastructure with a proven native or dependency replacement.
---

# Find Simplifications

Use `$architect-and-simplify` when installed; otherwise apply the same evidence
standard directly. A review or audit remains read-only unless the user asks to
implement a selected candidate.

## Ground The Survey

Read repository instructions, architecture and decision records, current
contracts, production callers, tests, docs, generated boundaries, and relevant
dependency policy. Protect intentional seams and multiple implementations until
fresh evidence beats their owning rationale.

A strong candidate removes or consolidates a real cost:

- a public method, event, option, registry entry, helper, package, durable fact,
  compatibility path, or test artifact has no production consumer;
- two representations, liveness mechanisms, caches, or state machines mirror
  the same authoritative fact;
- a separate package or abstraction adds publication, dependency, or caller
  knowledge without hiding meaningful complexity;
- speculative product generality has no current owner or reachable consumer;
- same-process typed data is defensively copied or validated as if it crossed a
  parser, queue, worker, process, durable file, model/tool JSON, or wire boundary;
- hand-rolled infrastructure can be replaced by a current platform primitive,
  standard library, or healthy dependency with net deletion after glue and
  residual semantics are counted.

Do not treat a typo, one tool's unused-symbol report, an intentionally recorded
backend, or "this looks complex" as a durable candidate without caller and owner
evidence.

## Prove Or Reject

Search exact symbols, wire strings, configuration keys, events, dynamic loader
paths, tests, docs, examples, and scripts, then read the call sites. For async or
stateful code, map each sentinel, promise, cancellation path, disposer, and flag
to an owner or transition; preserve distinct mechanisms that protect distinct
publication, rollback, callback, process, or quiescence guarantees.

For each candidate, state the current friction, owner/caller evidence, proposed
deletion or consolidation, behavior given up, migration and compatibility risk,
and verification path. Rank it `Strong`, `Worth exploring`, or `Speculative`.
Reject a candidate when a production caller exists, current rationale still
wins, or the change moves complexity without reducing the public behavior.

Use the repository's existing issue, ADR, RFC, TODO, or planning surface for a
durable proposal. Do not introduce Agent Notes or another proposal ledger. When
simplification supersedes a decision record, use `$dsh-archive-agent-notes` for
future-value retention judgment.
