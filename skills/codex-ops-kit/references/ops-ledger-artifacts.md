# Ops Ledger And Artifacts

Use this playbook for recurring ops, migration, sync-submit, cleanup, long command chains, durable deliverables, submission packages, public assets, helper scripts, AGENTS/skill updates, uploaded artifacts, and binary-backed package audits.

## Phase Ledger

Record each phase with timing, command, exit code, and evidence:

```bash
python3 scripts/phase_ledger.py run --ledger /tmp/phase-ledger.jsonl --phase local-preflight --command '<command>'
python3 scripts/phase_ledger.py append --ledger /tmp/phase-ledger.jsonl --phase remote --status skipped_unavailable --evidence '<probe output>'
```

Final reports should separate local completed, remote skipped/unavailable, external blocker, validation, and timing.

## Artifact Finalization

For durable deliverables or public-facing artifacts, create an early checklist covering:

- canonical source,
- rebuild command,
- package manifest,
- stale artifact cleanup,
- render or binary inspection,
- validator output,
- pathspec-safe diff,
- commit/push state,
- remote visibility when relevant.

## Durable Writeback

When a reusable lesson, stable command, source-of-truth boundary, or repeated failure class appears, write it to the nearest authority surface instead of leaving it only in chat.

Use this routing:

- Project or repo long-term rules: nearest scoped `AGENTS.md` or project docs/runbook.
- Release, CI, runtime authority, owner route, readiness, or currentness decisions: project docs/status, docs/decisions, closeout/attempt records, evidence ledgers, or existing owner receipts.
- Stable commands, tool boundaries, and reusable workflow mechanics: a dedicated skill, script README, or project tooling documentation.
- One-time execution evidence: task, attempt, closeout, journal, or a user-specified deliverable file.
- User-level Codex behavior: `~/.codex/AGENTS.md`, `~/.codex/prompts/*.md`, or the relevant local skill.

Writeback must include the trigger condition, source of truth, stable command or readback, verification method, and the path that should not be repeated. Do not promote one-off observations or unverified guesses into durable rules.

## Binary-Backed Packages

Audit JS shim/native boundaries before reading source or scanning home broadly:

```bash
python3 scripts/package_binary_audit.py /path/to/package --symbols '<symbol1,symbol2>'
```
