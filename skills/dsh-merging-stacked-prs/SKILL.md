---
name: dsh-merging-stacked-prs
description: Use when landing dependent pull requests or a PR stack; requires the platform's official stack support, live base/head verification, ordered checks, and owner-authorized merge state.
---

# Land A Pull Request Stack

This Skill is guidance for GitHub stacked PRs and is not merge or branch-delete
authority. Use `$develop-and-deliver` for the code and verification; use
`$task-mode-gate` when the requested landing is a real protected/public
mutation.

## Require Native Stack Semantics

Confirm the official stack extension or server feature is available before any
GitHub mutation. If it is unavailable, stop and report the missing capability;
when Flow is installed, use the Framework-projected repair action
(`opl packages repair --package-id opl-flow`) only when installation or repair
is authorized. Do not install an ad hoc extension or reproduce stack semantics
with a sequence of ordinary merges and retargets. Require every member to be in
the same repository and compare live authors, bases, exact heads, state, draft
status, approvals, checks, and official stack membership.

Establish bottom-to-top order from the live base chain. A partial landing must
name an explicit boundary and include every layer below it. Existing stacks with
unexpected members, order, authors, or trunk require user direction.

## Refresh And Validate

Use the platform-native stack sync/rebase path when a refresh is required. Record
the pre-refresh heads, use lease-protected publication, re-fetch rewritten heads,
re-audit scope and review state, and rerun each affected layer's evidence before
merging. Never use raw `--force` or infer readiness from a queued action.

## Merge And Close

Merge through the official stack API only. Wait for every selected PR to report
merged, verify remaining dependents still target the intended trunk or parent,
and delete branches only in a separate pass after zero open dependents. Read back
canonical commit/tree and keep archival or task lifecycle separate from GitHub
merge completion.
