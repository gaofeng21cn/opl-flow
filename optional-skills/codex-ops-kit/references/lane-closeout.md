# Git Lane Evidence

Use this playbook only for Git-backed worktree or subagent branch lifecycle events.

## Preflight

Resolve the intended target ref and report all worktrees:

```bash
python3 scripts/codex_ops_gate.py status --repo . --target-ref <target-ref>
```

The command fails closed for a non-Git path, an unresolved target ref, or a failed Git read. Dirty worktrees are evidence, not a global stop condition.

Require state only for the lane involved in the next action:

```bash
python3 scripts/codex_ops_gate.py status \
  --repo . \
  --target-ref <target-ref> \
  --require-clean-worktree <lane-path> \
  --require-current-worktree <lane-path>
```

Use `--require-current-worktree` only when that lane must be exactly at the target before the action. A feature lane with intentional commits is normally ahead and should be evaluated by the absorption audit instead.

## Lane Boundary

Before writes, identify the target ref, base ref, lane path, branch, allowed write set, verification command, and owner for unresolved decisions. Keep that task-local contract in the active plan or repo-native record; do not append a global ops ledger.

Do not modify unrelated dirty worktrees. Same-write-set conflicts, an unknown source of truth, an unresolvable target, or a missing owner decision must be resolved before writes or absorption.

## Absorption Audit

After the lane is clean and its verification is fresh, compare its commit set with the target:

```bash
python3 scripts/worktree_absorption_audit.py \
  --repo . \
  --base-ref <lane-base> \
  --target-ref <target-ref> \
  <lane-path>
```

Interpret the result:

- `exact-merged`: lane HEAD is an ancestor of the target.
- `tree-equivalent`: lane and target trees are identical.
- `patch-equivalent`: every lane patch is represented on the target, including cherry-picks with different commit IDs.
- `still-dirty`: uncommitted lane state remains.
- `ahead-not-absorbed`: the target is behind the lane.
- `deleted-without-evidence`: the requested worktree no longer exists.
- `needs-owner-review`: refs, repository identity, patch comparison, or history topology is not safely classifiable; non-equivalent lanes containing merge commits enter this class because `git cherry` does not prove merge-resolution equivalence.

Only the first three classifications return success and permit cleanup consideration. A successful classification does not replace diff review, repo-native tests, target-ref verification, or main-session acceptance.

## Cleanup

Delete a worktree or branch only after a cleanup-safe classification, main-session review, and fresh target verification. Then rerun `codex_ops_gate.py status` to confirm the remaining worktree inventory. Never reset, overwrite, or remove another owner's dirty write set.
