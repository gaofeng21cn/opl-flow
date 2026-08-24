# Codex App Owner Migration

This Skill coordinates task-level execution-owner migration through the native
Codex App surface. It moves the Beads/Dolt objective owner, not conversation
history, credentials, caches, private databases, or worktrees.

Use this reference together with `$opl-flow fleet` and the existing owner-migration
contract. OPL Fleet owns node admission and workspace currentness; Beads/Dolt
owns the durable objective and the compare-and-swap owner claim; the Codex App
owns the visible task/thread surface.

## Acceptance Boundary

A target is eligible only when all of these are freshly true:

1. The target host is visible through the native Codex App connection surface.
2. The target App exposes every required saved project in the Instance workspace
   profile, including the full OPL repository set needed by the objective.
3. The target task is created, handed off, or otherwise readable in the target
   Codex App, with matching host, project, workspace path, and task identity.
4. Fleet `doctor`, workspace `claim-check`, and Git currentness all pass.

An SSH session may bootstrap or inspect the target, but an SSH-launched
headless `codex` process is never accepted as a native App owner. SSH is an
acceptable transport only when the resulting task is independently visible and
readable in the target Codex App.

## Transaction

Run the following bounded sequence:

1. Read the Bead, current claim, write set, checkpoint, and source owner.
2. Preflight the target Codex App host and the complete Instance workspace
   profile before freezing source writes.
3. Create or hand off one target Codex App task in a saved target project.
4. Read the target task back from the native App and verify host, project,
   workspace, status, and task identity.
5. Prepare the source checkpoint, then perform exactly one owner CAS claim.
6. Require target acknowledgement and fresh target verification before source
   release. Keep Automation/singleton cutover as a separate CAS transaction.
7. Read back Beads/Dolt, the target App task, Git currentness, and the source
   release. Unknown transport outcomes are reconciled read-only before any
   retry.

The durable objective remains the same Bead. A new Codex App task is a valid
replacement executor; physically moving the original conversation is optional.
Do not create a second writer, duplicate Bead, duplicate Linear issue, or
second Supervisor heartbeat.

## Failure And Fallback

Classify failures explicitly:

- Before target claim: roll back the prepared migration and keep the original
  local owner active.
- After target claim: use a fresh reverse migration; never directly rewrite the
  pointer or resume both owners.
- Target App host/project/task not visible: stop the migration attempt as
  `blocked_external` or `on_demand`; do not substitute headless CLI execution.
- Workspace incomplete or only one OPL repository is present: fail preflight;
  do not claim a task that may later fail to package or publish.

Migration is optional for delivery. A failed migration must not cancel the
underlying objective or prevent the source owner from continuing locally.
When the user does not require another attempt, keep the capability registered
and record the migration experiment as stopped or On Demand according to the
Bead lifecycle class.

## Terminal Readback

Never report migration success from a project list, a running process, a lease,
an SSH connection, a test, or a handoff request alone. Success requires:

- native target Codex App task visible and readable;
- complete workspace/profile and Fleet admission current;
- one incremented Beads owner claim;
- target acknowledgement and verification;
- source release;
- Dolt push/pull parity and no duplicate writer.

If the native App route is unavailable, report that precise external gap and
continue the original objective locally. Do not convert the gap into a general
release blocker.
