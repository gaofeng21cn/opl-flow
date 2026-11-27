# AntiGravity Baseline Setup

OPL Flow can inspect and directly configure a machine's Google AntiGravity
environment (`~/.gemini/`) using the reusable templates in
`templates/antigravity/` and the `opl_workflow.py antigravity` CLI.

## What Gets Configured

| Layer | Target | Policy |
| --- | --- | --- |
| Global hygiene rules | `~/.gemini/GEMINI.md` | Managed marker block (`OPL_FLOW_AGY_BASELINE`), covering progress/cache hygiene, explicit Codex Supervisor delegation boundaries, and stall pullback; backs up and preserves all user rules outside markers; never overwrites overlapping unmarked sections. |
| `agy-fast` empirical overrides | `~/.gemini/config/plugins/agy-fast/rules/AGENTS.local.md` | Applied when `agy-fast` is installed; enforces `run_checks` `compact` default, single commands on native `run_command`, `apply_edits` <=5-file batches with `bestEffort`, and Swarm `--cli` syntax. |
| Progressive-disclosure Skills | `~/.gemini/config/skills/{swarm-code-worker-brief,third-party-audit-triage,project-vision-and-gap-review,opl-flow-dual-carrier}/SKILL.md` + optional `impeccable` symlink | Materializes bundled workflow & dual-carrier Skills and links `~/.agents/skills/impeccable` when present; flags duplicate `modern-web-guidance` symlinks if the official plugin is enabled. |
| Core & optional plugins (opt-in install) | `agy-fast` (required) + optional `codex-supervisor` & `modern-web-guidance-plugin` | `agy-fast` and `codex-supervisor` (used only when the user explicitly requests interactive Codex delegation/supervision; also installable via `agy plugin install https://github.com/cxgit12138/codex-supervisor`) are installed only when `--install-plugins` is explicitly passed. |
| Weekly read-only audit (opt-in) | `~/.gemini/config/sidecars/weekly-agy-env-audit/sidecar.json` | Created only with `--with-weekly-audit`; strict read-only permissions, never auto-enabled. |

## Commands

```bash
# 1. Inspect current AntiGravity baseline, rule budgets (<24KB), and 7-day telemetry
python3 scripts/opl_workflow.py antigravity doctor --json

# 2. Preview safe template updates without writing files
python3 scripts/opl_workflow.py antigravity apply --dry-run --json

# 3. Apply templates, overrides, and bundled Swarm brief Skill (with automatic backup)
python3 scripts/opl_workflow.py antigravity apply --json

# 4. Full new-machine setup including agy-fast plugin install and opt-in weekly audit
python3 scripts/opl_workflow.py antigravity apply --install-plugins --with-weekly-audit --tz Asia/Shanghai --json
```

Start a new AntiGravity session after applying changes so updated global rules
and skills are discovered cleanly. If `--with-weekly-audit` was requested,
enable the `AntiGravity Weekly Environment Audit` automation manually from the
Automations dashboard (`sidecar://dashboard`).

## Unified Multi-Carrier Event Routing (`auto`: Codex + AntiGravity + OPL DSH)

Once local carriers are installed (`opl-flow status --json` reports `codex.available`, `antigravity.available`, and/or `dsh.available`), OPL Flow runs **one unified zero-token background Router** (`--bridge auto` by default) that discovers active local chats and dynamically routes Codex, AntiGravity, and OPL DSH work against the same Beads/Dolt Ledger:

```bash
# Start one unified background router (defaults to --bridge auto)
opl-flow up

# Discover active local sessions across Codex, AntiGravity, and OPL DSH (agy + Gemini, etc.)
opl-flow sessions

# Override to a single explicit bridge only when needed
opl-flow up --bridge antigravity
opl-flow up --bridge codex

# Submit a task targeting AntiGravity or OPL DSH (optionally bound to an active session)
opl-flow send "Implement UI polish" --executor antigravity --write-set decision-dashboard/app.js
opl-flow send "Run DSH dual-model review" --executor dsh --session dsh:<session-id>

# Dispatch bounded worker slices directly across adapters
python3 scripts/opl_fleet.py dispatch run --adapter local-antigravity \
  --owner-task <objective-id> --handoff-json @handoff.json --use-antigravity-bridge
python3 scripts/opl_fleet.py dispatch run --adapter local-dsh \
  --owner-task <objective-id> --handoff-json @handoff.json --use-dsh-bridge
```

Unbound interactive chats detected by `opl-flow sessions` are surfaced for visibility and automatic workspace collision protection (`worktree_required_active_local_session`), without auto-creating Beads or consuming LLM tokens.

See [antigravity-baseline.md](../skills/opl-flow/references/antigravity-baseline.md)
for the full operational specification and safety boundaries.
