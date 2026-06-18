# Lane Closeout

Use this playbook for multi-worktree, multi-branch, subagent, handoff, resume, merge, delete, and closeout work.

## Gate

Run a read-only gate before starting, resuming, delegating, absorbing, cleaning, or claiming closeout:

```bash
python3 scripts/codex_ops_gate.py status --repo .
```

Use `--run-profile-checks` when a project profile defines safe current-truth commands. Use `--strict` when unresolved lanes, dirty worktrees, or failed profile checks should stop the action.

## Baton

Append a baton entry when opening, delegating, absorbing, stopping, or handing off a lane:

```bash
python3 scripts/codex_ops_gate.py append --repo . --lane <id> --event <started|handoff|absorbed|closed> --source-of-truth '<fresh command or file>' --allowed-write-set '<paths>' --forbidden-write-set '<paths>' --next-owner '<owner>'
```

Default ledger:

```text
~/.codex/state/codex-ops-kit/ledgers/<repo>-<hash>.jsonl
```

Use a project ledger only when it already exists and already owns active attempt/lane truth.

## Delegation Contract

Use subagents only for independent read-only audits, isolated verification, or clearly separable implementation lanes with disjoint write sets.

The first line of every delegated task must state:

```text
任务: <one sentence> | cwd: <absolute path> | 权限: read-only/workspace-write | source of truth: <file/command/URL> | 停止条件: <done/blocker/timeout condition>
```

Also state the allowed write set, forbidden write set, expected verification command, and output format when writes are allowed.

Delegated agents must not spawn subagents, widen scope, run destructive git operations, or change the source of truth. If scope expansion appears necessary, they should report the reason and suggested next step instead of acting.

## Multi-Lane Boundaries

For "together", "all the way", "parallel worktree", or "do everything safe" requests, create lane boundaries before dispatch:

- lane id and objective,
- source of truth,
- allowed and forbidden write sets,
- target branch or base ref,
- verification command,
- stop condition,
- owner for unresolved decisions.

Dirty files block only the same write set. Existing local commits, ahead/behind state, and stale main refs are preflight work: fetch, check ancestor/fast-forward relationships, and choose root checkout or isolated worktree based on source-of-truth safety.

Only mark a lane blocked when the same write set conflicts, the semantic owner is unclear, verification cannot cover the lane, remote state cannot be absorbed safely, permissions are missing, or a real owner decision is required.

## Concurrent Root Checkout Dirty

When supervising concurrent Codex threads or lanes, a dirty shared root checkout is a work-location defect, not a reason to wait indefinitely or stop the original task.

1. Identify the owner lane before acting:
   - read `git status --short --branch`,
   - map dirty paths to known lane write sets,
   - inspect the ops ledger with `codex_ops_gate.py status --repo .`,
   - use thread tools such as `read_thread` when available to find the active conversation that produced or owns the dirty write set.
2. If the owner conversation is active, send precise steering instead of taking over:
   - tell it to stop creating new root-checkout writes,
   - migrate or absorb the existing dirty diff into an isolated worktree for that lane,
   - continue its original task inside that worktree,
   - verify there, then absorb back to `main` and clean up.
3. Do not block unrelated lanes. A root dirty write set should not prevent other worktrees with disjoint write sets from continuing.
4. Do not overwrite, reset, checkout, or reformat another owner's dirty files. The supervising lane may take over only when the owner is inactive, explicitly hands off the write set, or the ownership gate says the current lane may claim it.
5. Close the incident only after root checkout is clean or the dirty write set has an explicit active owner/worktree handoff with a verification and absorption plan.

## Main-Session Acceptance

Do not treat a subagent report, local commit, merged worktree, or passing focused test as final completion by itself.

The main session must:

1. inspect the diff or read-only evidence,
2. confirm the lane stayed inside its write set and stop condition,
3. rerun the verification command or collect equivalent fresh evidence,
4. map the lane back to the user's original plan, accepted work order, or audit item,
5. absorb, push, hand off, or explicitly reject the lane,
6. clean up temporary worktrees/branches when safe.

For all-the-way or full-plan requests, closeout must use the original plan as the audit table. A narrow implementation slice, commit summary, focused test suite, or "lanes absorbed" status can prove only the matching plan rows. If the original plan contains broader target-state rows, keep those rows as `partial`, `not_started`, or `blocked` with current evidence.

## Worktree Absorption

Before merging, deleting, or declaring a lane absorbed, audit against the target ref:

```bash
python3 scripts/worktree_absorption_audit.py --repo . --target-ref main <worktree-path>
```

Treat `exact-merged` and `content-equivalent` as cleanup candidates. Treat `still-dirty`, `ahead-not-absorbed`, `deleted-without-evidence`, and `needs-owner-review` as closeout work, not completion evidence.

## Closeout Claim

A lane is closed only when the target write set is absorbed, verification is fresh, unresolved baton items are closed or handed off, and the final response names any residual blocker.
