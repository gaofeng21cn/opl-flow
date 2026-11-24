# AntiGravity Baseline Setup

OPL Flow can inspect and directly configure a machine's Google AntiGravity
environment (`~/.gemini/`) using the reusable templates in
`templates/antigravity/` and the `opl_workflow.py antigravity` CLI.

## What Gets Configured

| Layer | Target | Policy |
| --- | --- | --- |
| Global hygiene rules | `~/.gemini/GEMINI.md` | Managed marker block (`OPL_FLOW_AGY_BASELINE`), backs up and preserves all user rules outside markers; never overwrites overlapping unmarked sections. |
| `agy-fast` empirical overrides | `~/.gemini/config/plugins/agy-fast/rules/AGENTS.local.md` | Applied when `agy-fast` is installed; enforces `run_checks` `compact` default, single commands on native `run_command`, `apply_edits` <=5-file batches with `bestEffort`, and Swarm `--cli` syntax. |
| Progressive-disclosure Skills | `~/.gemini/config/skills/swarm-code-worker-brief/SKILL.md` + optional `impeccable` symlink | Materializes the Swarm brief Skill and links `~/.agents/skills/impeccable` when present; flags duplicate `modern-web-guidance` symlinks if the official plugin is enabled. |
| Core resident plugins (opt-in install) | `agy-fast` (and optional `modern-web-guidance-plugin`) | Installed via official owner installer only when `--install-plugins` is explicitly passed. |
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

See [antigravity-baseline.md](../skills/opl-flow/references/antigravity-baseline.md)
for the full operational specification and safety boundaries.
