# RHO Retrospection

Use this playbook when running `wbopan/retro-harness`, auditing Codex session history, or absorbing RHO candidates.

## Default Run

Run RHO through the wrapper first. It preselects a bounded session set, caps huge rollout files for small budgets, and defaults to `--no-apply`:

```bash
python3 scripts/rho_wrapper.py --project . --budget tiny
python3 scripts/rho_wrapper.py --project . --budget tiny --run
```

Budgets: `micro`, `tiny`, `small`, `medium`, `full`.

Use `--allow-apply` only after reviewing the staged winner and deciding the target is the correct authority layer.

## First-Pass Or Cross-Project Runs

Summarize before asking RHO to digest large raw rollouts unless intentionally doing a full pass:

```bash
python3 scripts/rollout_summarizer.py --project . --since-days 30 --max-sessions 16 --max-rollout-kb 4096 --output /tmp/codex-rollout-summary.json
```

Full and cross-project first passes may run long. Use wrapper heartbeat, `stalled_artifact=true`, final `report.md`, and `--no-apply` winner as evidence. Do not draw conclusions from temporary candidate files.

## Absorption

RHO candidates are inputs, not patches to apply blindly. Classify every winner by authority before editing:

- cross-repo Codex workflow rule,
- user-level skill or helper script,
- project profile adapter,
- project-owned fact, status, contract, runtime truth, owner route, or validation entry,
- reject.

Write the result to the lowest durable authority that owns the behavior:

- Use user-level `AGENTS.md`, prompts, skills, or tools for task-agnostic Codex behavior.
- Use project `AGENTS.md`, contracts, docs/status, runtime outputs, owner receipts, or profiles for project facts.
- Use `~/.codex/state/codex-ops-kit/` for generic Codex lane baton state.
- Use a project ledger only when that ledger already exists and already owns equivalent truth.

Do not promote project paths, candidate-created ledgers, historical conclusions, release artifact names, runtime status, owner routes, or docs-only claims into global rules.

Absorb only task-agnostic guardrails, stable commands, and reusable scripts globally. Keep project facts, owner routes, runtime truth, release artifacts, paths, and historical conclusions in project authority surfaces.
