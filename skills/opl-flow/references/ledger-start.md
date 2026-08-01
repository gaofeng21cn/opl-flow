# Ledger Start

Use this reference only after reading `start-onboarding.json`.

## Idempotent Onboarding

1. Resolve the current saved project, local environment, unique private
   Instance, and objective fingerprint. Ask only on material ambiguity.
2. Use native Codex project/task tools to reuse one matching Dashboard and pin
   it. Create only when none exists; multiple matches fail closed.
3. Pull the Instance Ledger. Reuse the Bead whose `external_ref` is exactly
   `codex://thread/<thread_id>`, or create one when absent. Never initialize a
   second Ledger.
4. Parse `$CODEX_HOME/automations/*/automation.toml` to discover the one hourly
   heartbeat bound to the Dashboard and objective. Unreadable or ambiguous
   discovery fails closed. Use native Automation view/update; never create a
   cron workaround or second loop.
5. Configure a supervisor, not a passive poller. Each run reads ready,
   in-progress, overdue, and live execution tasks; chooses one allowed decision
   per lane; performs continuation, correction, split, merge, idle-event, or
   terminal review; and writes claim/checkpoint/blocker/remaining to Beads.
6. Reconcile every user-ledger Bead to exactly one Linear issue through the
   official Connector, preserving hierarchy and the narrow field contract.
7. Push and read back Dolt only after coherent mutation. Finish with exact
   Dashboard, Bead, heartbeat, Linear coverage, and Dolt parity.

## Linear Field Authority

Linear to Beads: human intent, priority, due, `codex-ready`, cancel.

Beads to Linear: execution state, blocker, result.

Project only identity, title, hierarchy, status, priority, due, readiness,
cancel intent, short blocker/result, and links. Exclude credentials, local
paths, logs, full notes, metadata, and checkpoints. Do not use `bd linear sync`.

Beads/Dolt is task SSOT. Linear is the complete human-readable projection;
GitHub carries delivery evidence; Fleet carries capacity. Do not use Codex
Cloud for this route and do not archive without fresh user approval.
