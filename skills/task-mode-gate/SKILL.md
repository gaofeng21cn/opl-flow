---
name: task-mode-gate
description: Use only when the task will perform or reconcile a release, deployment, migration, public or destructive mutation, cross-carrier version change, or validation-to-production transition. Excludes plans, reviews, ordinary development, tests, and dry-runs.
---

# Task Mode Gate

Constrain an actual production or high-risk mutation without turning production
sequencing into a general development methodology. This skill never grants
product, repository, release, or external write authority.

## Stop Ladder Handoff

OPL Flow's `task_boundary_policy` runs before this Skill. Expand into this gate
only when a supported Stop Ladder reason exists and the requested change
actually crosses a release, deployment, migration, public, destructive, or
validation-to-production boundary. The Stop Ladder does not grant mutation
authority. Once handed off, this Skill remains the owner of production mode,
mutation scope, idempotency, reconciliation, and final owner-authoritative
readback.

## Exit When Not Applicable

Do not apply this skill because a plan, document, issue, or conversation merely
mentions release, deployment, migration, or another trigger noun.

For a read-only task, use the internal disposition `not_applicable` and continue
without a mode declaration. The only read-only exception is bounded
reconciliation after an unknown public-mutation result. Tests and dry-runs are
also out of scope unless the production gate itself is what the task validates.

## Record Internally

Before the first mutation, derive and retain this five-field checklist:

```text
mode: development_validation | production_release
mutation_scope: read_only_reconcile | local_write | public_mutation
terminal_outcome:
keep_gates:
defer_gates:
```

Treat the checklist as control state, not a chat artifact. Do not quote,
announce, or render it unless the user explicitly asks for a gate audit.
Recompute it silently only when `mode`, `mutation_scope`, or
`terminal_outcome` materially changes.

## Communicate Only When Needed

Default to quiet operation. For a clear, authorized mutation, continue with
ordinary progress updates and do not add a separate gate preamble or structured
field block. If the host requires a skill-use announcement, fold it into one
natural clause without exposing the checklist or internal labels.

Use visible gate communication only when it changes the user's decision or
expectation:

- give at most one sentence when a validation-to-production transition changes
  the active authority or target;
- ask a blocking question when authority is missing, the target is ambiguous,
  or an irreversible or destructive action still requires confirmation;
- give a concise reconcile notice when a public mutation has an unknown result,
  stating that no retry will occur before owner-authoritative readback.

Show the full checklist only when the user explicitly requests it or an
owner-required audit artifact needs it. Prefer the audit artifact over inserting
the checklist into ordinary conversation.

## Classify Gates

Use `development_validation` only when the task is implementing or validating
the production gate, or is exercising a bounded non-production mutation. Keep
the gates that protect the object or mutation being validated. Defer unrelated
production release order, cross-product binding, final channel currentness, and
downstream sequencing.

Use `production_release` for the real release, deployment, migration,
destructive action, protected handoff, channel promotion, or public mutation.
Enable the repository's actual authority, ordering, qualification, and final
owner-authoritative readback.

A production gate belongs in development only when that gate itself is being
implemented or validated.

## Preserve Mutation Safety

Every `public_mutation`, in either mode, keeps:

- exact inputs, target namespace, and authority or permission boundaries;
- immutable artifacts and a single writer for the target;
- idempotency or compare-and-swap where the target supports it;
- fail-closed handling for the same name with different bytes or digest;
- bounded read-only reconciliation after timeout or unknown external result;
- final readback from the public or owner-authoritative surface.

Development evidence must not be presented as a production release or
production-ready claim.

For `read_only_reconcile`, inspect the owner-authoritative surface and do not
rerun, redispatch, cancel, or guess the external result.

## Transition To Production

Reclassify to `production_release` after the technical path is proven and the
production inputs and authority are available. Reclassify the deferred gates,
run the production owner route, and verify the final production surface. Surface
a compact notice only when the transition changes the user's expectation or
required authority; do not treat the successful development run as that
transition.
