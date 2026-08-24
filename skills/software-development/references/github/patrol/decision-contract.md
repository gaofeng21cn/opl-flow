# Decision Contract

Load this reference only for new or changed PR/issue intake or when preparing a
GitHub mutation.

## Pull Request Intake

Record these fields before any PR-specific test or mutation:

```text
repo=<owner/repo>
number=<number>
head_sha=<sha>
base_sha=<sha>
default_branch_sha=<sha>
updated_at=<timestamp>
ssot_fit=aligned|partially_aligned|conflicting|unknown
real_bug_evidence=<current-main reproduction or deepest proven breakpoint>
feature_or_policy_delta=<none or explicit delta>
canonical_owner=<owner surface>
user_visible_impact=<observable impact>
ssot_surfaces_touched=<contracts/source/runtime owners>
artifact_language=en|zh|<explicit language>
language_basis=explicit_user_choice|repository_rule|item_dominant_language|new_item_request_language
language_state=consistent|repair_required|not_applicable|unknown
decision=fix|split|request_evidence|close|no_change
```

Missing fields prohibit `actionable_auto`. `unknown` caused by auth,
transport, connector coverage, quota, or tooling prohibits close and other
semantic mutation.

Classify the item:

- `actionable_auto`: `ssot_fit=aligned`, a fresh real bug is proven, one owner
  and writable lane exist, the diff is proportionate, and repo-native
  verification can close without additional authority.
- `actionable_manual`: the target is reasonable but needs product/policy
  choice, third-party branch work, approval, release/install/publication,
  secret, external input, or an irreversible operation.
- `needs_evidence`: the target, current reproduction, or proposed route is not
  proven. Name the smallest missing evidence.
- `already_integrated`: canonical main contains the same semantics, supported
  by commit/tree/blob/test/runtime evidence.
- `duplicate_or_superseded`: identify the exact successor or current owner.
- `not_actionable`: the target conflicts with current SSOT, belongs to another
  owner, duplicates parallel truth, or causes a reproducible regression.

For a multi-objective PR, assess each objective separately. One real bug never
authorizes unrelated feature, policy, identity, lifecycle, or review changes.
If it cannot safely converge in place, request the minimal split, close the
superscoped PR, and invite a fresh narrow PR or an issue. Do not close when the
only uncertainty is patrol-side read failure.

## Issue Intake

Use the same authority order and record repository, issue number, updated time,
default SHA, reproduction/breakpoint, canonical owner, impact, labels,
linked PR/commit, artifact language, language basis, language state,
classification, and decision.

Classifications mirror PR intake: `actionable_auto`, `actionable_manual`,
`needs_evidence`, `already_fixed`, `duplicate_or_superseded`, and
`not_actionable`. An issue title or reporter diagnosis is not a reproduction.

## CI Currentness

- Inspect default-branch, current release-owner, and open-PR-head surfaces.
- Empty `statusCheckRollup` requires a head-SHA Actions/check-suite fallback.
- Distinguish `failure`, `startup_failure`, `action_required`, `queued`,
  `in_progress`, `cancelled`, and true zero-run states.
- Fold a historical failure only when a later terminal success covers the same
  workflow name, branch/authority, and relevant source.
- CI failure is not automatically a product bug. Check whether code behavior,
  a contract, a test expectation, a workflow, a runner, a secret, or an
  external provider is the deepest proven breakpoint.

## GitHub Write Contract

For every write, record:

```text
operation_id=<stable id>
owner_id=<unique owner>
target=<repo and item/run/ref>
precondition=<head/base/state/marker/permission readback>
artifact_language=<resolved language>
language_precondition=<consistent|repair_required|not_applicable|unknown>
mutation=<one bounded action>
result=<returned id/state>
postcondition=<fresh exact readback including language consistency>
```

Use one evidence-bearing comment, not daily progress comments. For a third-party
PR classified `needs_evidence`, `not_actionable`, `duplicate_or_superseded`, or
superscoped, the caller may authorize comment-then-close as one operation.
Explain concrete re-entry conditions and welcome a narrow new PR, issue, or
maintainer reopen. This does not authorize approve, merge, push, or fork edits.
