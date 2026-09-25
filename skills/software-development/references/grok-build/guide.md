# Grok Build Agent

Use one persistent, tool-executing Grok Build session as the implementation owner. Codex owns scope definition, session supervision, independent verification, and any canonical integration the user did not explicitly delegate.

## Establish The Delegation

1. Resolve the repository authority, writable worktree, branch, exact write set, forbidden surfaces, current checkpoint, terminal outcome, and allowed external mutations.
2. Put the complete task contract in a handoff file outside the repository. Read [handoff contract](handoff-contract.md) when drafting it.
3. Start Grok in the writable worktree with [scripts/run-grok-build-agent.sh](../../scripts/run-grok-build-agent.sh). The surrounding `exec_command` must use `tty: true` and yield after about one second so the session remains available through `write_stdin`.
4. Pass task-specific `--deny` rules after `--`. They supplement the handoff; they do not broaden authorization.

Example:

```text
<software-development-skill>/scripts/run-grok-build-agent.sh start <worktree> <handoff-file> -- \
  --deny 'Bash(git push*)' \
  --deny 'Bash(*deploy*)'
```

Do not use `-p`, `--single`, `--output-format`, or a short `--max-turns` limit for a multi-step delivery. Those forms turn the run into a bounded response job and make durable supervision or recovery unreliable. A one-shot mode remains appropriate only for a genuinely one-step, read-only query.

## Supervise One Owner

Supervision is an observational and corrective role, not a wall-clock watchdog. Keep one Grok writer and let it think for as long as the task needs when it is still live or has a recoverable child command.

### Preserve normal long-running work

- Keep the returned exec session alive and use empty `write_stdin` polls or a bounded wait for observation. Prefer a sparse 30-60 second cadence during long phases and shorten it only around a known transition or incident. A quiet PTY, spinner, long reasoning interval, or unchanged diff by itself is not a stall and is never a reason to interrupt.
- Classify each observation as `thinking`, `tool-running`, `child-running`, `completed/idle`, or `stalled/failed`. For the first three, continue waiting and inspect the real owner surfaces only as needed: `git status`, `git diff`, `HEAD`/tree, test output, artifacts, logs, PID, or runtime readback.
- Do not send artificial keepalive or `continue` prompts merely to produce chat output. Send a prompt only when there is a concrete discrepancy, a needed decision, or a bounded recovery action.
- A `completed/idle` Grok process with a non-empty diff or exact commit and the required evidence is successful, not stuck. Leave the session available through Codex closeout; terminate it only as explicit, authorized cleanup.
- Long-running child commands may continue after Grok yields. Recover their PID/log/receipt and wait for the original writer rather than launching a duplicate.

### Correct only on evidence

- Suspect `stalled/failed` only when there is explicit failure, the owner process/session has exited without a terminal result, or a task-appropriate observation window shows no process/child activity and no external owner-surface movement. There is no universal short timeout; expensive builds and analysis require a longer window.
- Before any stop or takeover, record the current phase, last durable marker, process/child state, and fresh external progress marker. A `write_stdin` poll that returns no new text is not itself a failure.
- If Grok narrates a change but the worktree did not move, send the exact discrepancy back to the same live session and require tool evidence. Do not silently implement the task as Codex.
- Give corrections as short deltas to the handoff. Avoid resending full history or asking Grok to rediscover settled facts.

Treat a tool-channel failure as a bounded incident:

1. Record the failing effective tool/error and a fresh external progress marker such as `HEAD`, diff stat, or the expected artifact. Do not classify ordinary reasoning silence or an empty PTY poll as a tool failure.
2. Send one short correction to the same session requiring the smallest relevant tool call and its real output. Do not restart the session merely because of a model-list refresh warning.
3. Clear the incident if that tool succeeds or an external owner surface advances.
4. If the same effective tool fails again, Grok exhausts its internal retries, or it repeats a completion claim while the progress marker remains unchanged after the correction, stop the live writer and report `BLOCKED` at the Grok tool layer. Preserve the Grok session ID, relevant log/error, and external progress marker for recovery. Do not loop, start a second writer, or take over implementation as Codex.

## Recover The Session

If the live exec session is lost, identify the Grok session ID from its output or `~/.grok/sessions`, then run:

```text
<software-development-skill>/scripts/run-grok-build-agent.sh resume <worktree> <grok-session-id>
```

The start command stores model, reasoning effort, permission mode, worktree, and deny arguments in task-specific Git metadata. Resume reuses that launch receipt and rejects conflicting environment overrides or deny arguments. For a session created before receipt support, first recover its exact launch settings from the original command or log, then perform a one-time adoption with `GROK_BUILD_ADOPT_LEGACY_RECEIPT=1` and the exact original environment overrides and deny arguments; never guess them. Again use `tty: true`. Send the next instruction through the resumed session. Start a new Grok session only after the previous owner is confirmed stopped and the worktree/current process state has been freshly read back. If the original process is still alive but visually idle, do not resume or start another session: classify it as `thinking`, `child-running`, or `completed/idle` and continue observing the original owner.

Treat transient model-list refresh warnings separately from actual tool failures. A warning is not a blocker when the selected model and tools continue to run. Diagnose from the Grok session log and external worktree evidence before changing authentication or installation.

## Verify And Close

After Grok reports completion:

1. Independently inspect the complete task-owned diff or exact commit against the fresh authority.
2. Check scope, callers, invariants, and forbidden side effects; do not accept Grok's summary as evidence.
3. Run the narrow tests and terminal acceptance required by the repository and user.
4. Report Grok implementation and Codex verification separately.
5. Commit, push, publish, deploy, integrate, or clean up only when those actions are within the user's authorization. A local diff is not canonical delivery.
