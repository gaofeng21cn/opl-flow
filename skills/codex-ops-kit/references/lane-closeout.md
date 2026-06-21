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

## Goal-Driven Executors and Heartbeat Supervisors

For durable multi-thread missions, do not make an executor heartbeat the primary progress driver. The executor thread should hold an active goal that defines the mission, stop conditions, allowed write set, verification, and absorption reporting. Heartbeats may be used as temporary recovery safety nets, but once the executor goal is active they should be paused or treated as fallback-only so repeated one-shot prompts do not distort the mission.

Use heartbeat automation for supervisor or auditor threads when periodic fresh readback, steering, and intervention are the actual job. Each supervisor heartbeat should check whether the executor is idle, lacks an active goal, prematurely marked the goal complete, treated a checkpoint as mission closeout, or produced an unabsorbed worktree candidate. If any of those conditions hold, the supervisor should steer the executor immediately instead of waiting for another interval.

Distinguish a turn checkpoint from mission closeout. A work-unit result such as an owner receipt, artifact delta, reviewer or gate delta, stable typed blocker, human gate, route-back, `no_absorption_needed`, or a focused test pass can close the current turn only when it satisfies that turn's stop condition. It does not complete the durable mission unless the original user goal, main session acceptance, or an explicit owner decision says the mission is closed.

## Mission Artifact Progress Guard

For durable domain missions, keep the user's target artifact as the primary progress metric. Repo absorption, worktree hygiene, fresh readback, queue state, tests, currentness repair, provider liveness, and control-plane cleanup are supporting ops evidence; they are not mission progress unless the original mission was explicitly an ops mission.

Every executor, supervisor, and main-session report should classify the latest delta as one of:

- `mission_artifact_delta`: a target artifact, deliverable, decision packet, owner receipt, accepted gate/reviewer delta, stable typed blocker, human gate, route-back, or next owner handoff moved.
- `platform_or_observability_delta`: code/test/read-model/currentness/runtime/queue/telemetry/absorption work moved, but the target artifact did not.
- `blocked_with_owner`: the target artifact cannot move until a named owner supplies input, authority, permission, or a decision.

When a governed runtime path is blocked and the project allows a foreground/manual mode, steer the executor to produce a clearly labeled manual work product or owner-decision packet instead of looping on more status reads. That manual work product must not be represented as governed runtime truth until the owning project surface consumes, accepts, rejects, or blocks it.

Do not let `blocked`, `waiting_human`, `not_actionable_without_owner`, missing live session, or owner-route authority gaps become mission closeout for a user goal that explicitly asks to continue until a target deliverable exists. Treat them as escalation triggers: the executor continues the milestone deliverable, the supervisor steers or opens a repair lane, and the main session owns absorption or takeover when needed.

## Mission-First Repair Lanes

When a domain mission exposes platform, runtime, control-plane, currentness, or owner-route defects, do not let the mission executor become a platform-repair sink. Keep the target artifact moving while the defect is routed through a repair lane.

### Root-Cause Depth Guard

For durable missions, multi-thread supervision, heartbeats, runtime/currentness/readiness claims, and repeated stalls, a report must not close at symptom depth.

Use this ladder:

- `L0 symptom`: the visible state, such as blocked, idle, no live session, queue empty, handoff required, stale, failed, or waiting.
- `L1 direct boundary`: the command, projection, owner route, gate, queue, contract, dependency, or artifact boundary that emitted the symptom.
- `L2 cross-surface evidence`: at least one neighboring truth surface that proves whether the boundary is current or stale, such as global runtime state vs per-study projection, owner receipt vs pending candidate, source file vs generated view, or terminal closeout vs live readback.
- `L3 owner repair path`: the named owner surface, allowed and forbidden write sets, verification/readback, and whether the next action is code repair, contract repair, owner consumption, human gate, or typed blocker.
- `L4 prevention`: why existing workflow allowed the issue to recur and which prompt, runbook, skill, contract, or automation should prevent recurrence.

Minimum closeout:

- One-off status audit may stop at `L2` only if the user asked for observation only.
- Repeated stalls, supervisor heartbeat findings, currentness drift, false progress/readiness claims, or repair-lane proposals require `L3`.
- "Thorough", "root cause", "fix it", "do any intervention", or "do not stop" requests require `L3` plus either a concrete repair lane, owner decision path, or `L4` writeback recommendation.

Reports that only rename a symptom, for example "it is stopped because it is blocked" or "no progress because no live session", are incomplete and must steer, investigate, or escalate instead of closing.

Use this split:

- mission executor: keeps producing the target artifact, governed owner handoff, foreground/manual work product, owner decision packet, stable blocker, or human gate.
- supervisor: classifies the discovered defect, steers the executor away from runtime-only loops, and either prepares a non-conflicting repair candidate or proposes a separate repair lane.
- repair lane: owns the platform/code/runtime fix in an isolated worktree or clearly scoped branch.
- main session: absorbs verified repo candidates to the target ref unless explicitly handed off.

Each discovered defect must be classified as one of:

- `absorbed_to_main`: the repair is already on the target ref and fresh evidence confirms the target behavior.
- `candidate_ready_for_absorption`: an isolated worktree/branch has a commit, diff, verification, readback, residual risk, and absorption packet.
- `open_repair_lane_proposal`: root cause or strong hypothesis exists, but no repair lane is active yet; report owner surface, allowed/forbidden write sets, verification, and stop condition.
- `not_actionable_without_owner`: continuing requires a human, runtime owner, credential, lease, permission, or cross-repo authority decision.
- `not_blocking_mission_progress`: record the defect as supporting work but keep the mission executor focused on the artifact.

Create or propose a repair lane when the defect repeatedly blocks the same mission work unit, prevents owner-surface consumption of a mission artifact, causes false progress/readiness claims, makes target-ref and executor-worktree readbacks disagree, or belongs to a cross-repo/runtime owner path that the mission executor cannot legally repair.

Do not create a repair lane for status wording, telemetry polish, generic cleanup, test-only green bars, or speculative issues without a root-cause boundary. Do not hand-write domain truth, owner receipts, typed blockers, human gates, publication authority, package authority, runtime-owned queues, or provider attempts to simulate a fix.

Repair-lane closeout requires the normal absorption classification plus mission impact:

- what target artifact or owner path it unblocks;
- why the mission executor should or should not wait for it;
- how the mission continues while the repair is pending;
- who absorbs and pushes the repo candidate;
- what fresh readback proves the repair has reached the target ref.

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
