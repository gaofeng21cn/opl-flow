# Decision Contract

Load this reference only for new or changed PR/issue intake or when preparing a
GitHub mutation.

## Pull Request Intake

Resolve the author's trust tier before deciding which proposal requirements
apply. Use the latest direct owner instructions and the caller-designated private
collaboration register on its trusted canonical base. Keep the public admission
policy generic; account mappings, numeric IDs, partner scopes, and departure
reasons belong only in that private register. Match the immutable GitHub user ID
and the exact target repository. A PR cannot elevate its author by editing a policy, allowlist, or
`AGENTS.md` in its own head. Display names, `author_association`, write access,
and earlier merged PRs are not a trust grant.

Read the register's current authoritative revision before classification; record
its revision in the caller's private audit. An absent entry in a successfully
read, complete register means `third_party`. An unreadable, stale, or conflicting
register means `unknown`; reconcile it before a trust-dependent decision, and
continue unrelated work. Do not publish the register, account relationships,
internal trust judgments, private locations, or departure reasons in public
comments, payloads, fixtures, or consumer repositories. Public replies explain
the proposal's evidence and product fit.

- `owner_operated`: the owner and explicitly confirmed self-operated accounts.
  Trust their product intent and proceed directly to merge within the caller's
  authorization. Do not demand an Issue, a necessity argument, or an additional
  subjective product approval. Preserve actual permissions, branch protection,
  conflict handling, deterministic checks, and data-integrity boundaries.
- `repo_partner`: an explicitly confirmed development partner for this exact
  repository. Start from trust, check the latest SSOT and actual diff, and use
  proportionate verification. Do not mechanically impose third-party Issue
  prerequisites. Resolve concrete conflicts rather than accepting every change.
- `third_party`: everyone else, including a partner outside their named
  repository scope. Start from skepticism of the proposal's diagnosis and
  necessity. Only an easily reproducible, clearly understood Debug fix that
  restores intended behavior may proceed without an Issue. Unreproduced Debug,
  intentional behavior changes, and new capabilities require a substantive
  linked Issue and supporting evidence. The submitter must demonstrate why a
  behavior change or core feature is necessary; the maintainer independently
  decides whether it belongs in the current product.

Names such as `fix`, `compatibility`, or `alignment` do not establish that a
change is Debug. A disputed product design can be intentional. Compare actual
before/after behavior with the latest SSOT and separate real defect correction
from added restrictions, changed defaults, expanded permissions, or features.
An Issue link, edited contract, generated test, green CI, or mergeability does
not establish necessity. Do not invent a requirement or complete the
submitter's missing justification in order to absorb their proposal.

For third-party proposals missing a required Issue, explanation, or evidence,
explain the precise gap and close the PR under the caller's authorization;
invite the contributor to complete the Issue and submit a new focused PR.
An Issue is an input to judgment, not automatic feature approval. Authentication,
transport, quota, or tooling failures on the maintainer's side are unknown
observations and never grounds for that closure.

Record the applicable fields before a PR-specific test or mutation:

```text
repo=<owner/repo>
number=<number>
head_sha=<sha>
base_sha=<sha>
default_branch_sha=<sha>
updated_at=<timestamp>
author_id=<immutable GitHub user id>
author_tier=owner_operated|repo_partner|third_party|unknown
author_scope_basis=<private register revision or direct owner instruction and exact repository; private audit only>
change_kind=debug|unreproduced_debug|behavior_change|feature|mixed
issue_requirement=exempt|not_required_reproduced_debug|required
issue_evidence=<linked Issue and submitter evidence or exemption basis>
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

Missing applicable fields prohibit `actionable_auto`. `unknown` caused by auth,
transport, connector coverage, quota, or tooling prohibits close and other
semantic mutation.

Classify the item:

- `actionable_auto`: the applicable trust-tier path admits the work, one owner
  and writable lane exist, and the actual permission and verification boundaries
  are satisfied. Owner-operated intent needs no independent necessity proof.
  A partner's change needs an SSOT check. A third-party change needs either a
  clearly reproduced defect or an independently justified Issue-backed proposal.
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

For a multi-objective third-party PR, assess each objective separately. One real
bug never authorizes unrelated feature, policy, identity, lifecycle, or review changes.
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
