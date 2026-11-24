# AntiGravity Experience Baseline

Use this reference for `doctor`, `setup`, `tune`, and `update` when the request
targets Google AntiGravity (`~/.gemini/`).

## Design Principles

AntiGravity imposes concrete runtime budgets and isolation boundaries:

1. **Rule budgets**: Always-on rules are capped at `24 KB` per file and share a
   `20,000`-token aggregate budget. Keep `~/.gemini/GEMINI.md` lean and limited
   to cross-project durable hygiene; keep repo facts in each repository's
   `AGENTS.md` and repeated multi-step runbooks in progressive-disclosure Skills.
2. **Minimal resident plugins and eager MCPs**: Every `eager: true` MCP tool is
   injected into every session's system prompt and competes in tool routing.
   Keep global resident plugins minimal (`agy-fast` for batched search/outline/edit/checks
   and `SessionStart` snapshots, plus `modern-web-guidance-plugin` for web work).
   Do not double-load a standalone `modern-web-guidance` skill symlink when the
   official plugin is enabled.
3. **Prompt Cache and multimodal hygiene**:
   - Avoid unnecessary Plan Mode toggling inside implementation loops (changing
     the system prefix is a primary Prompt Cache miss driver).
   - Keep visual inspections out of long (>150k token) coding sessions by
     delegating image reads to `research` subagents and isolating user-pasted
     troubleshooting screenshots to short sessions.
   - Recommend `/compact` or a fresh session between major phases once context
     approaches 150k–200k tokens.
4. **Swarm worker isolation**: AntiGravity does not mount MCP servers,
   `user_rules`, or `SessionStart` snapshots into Swarm workers. Coordinator
   briefs for coding/audit workers must include owned paths, explicit
   `agy-fast --cli` syntax (`--text`/`--regex`/`--glob`/`--git`, `outline`,
   `edit --best-effort --stdin`, `check --compact`), and acceptance commands.

## Authoritative Baseline Assets

The machine-readable AntiGravity baseline lives in `templates/antigravity/`:

- `templates/antigravity/baseline-manifest.json` — declarative plugin, skill,
  rule, budget, duplicate-avoidance, and optional weekly-audit specification.
- `templates/antigravity/GEMINI.md` — reusable global AntiGravity rules block.
- `templates/antigravity/agy-fast-AGENTS.local.md` — empirically tuned
  `agy-fast` local overrides (`run_checks` `compact` default, single lightweight
  command on native `run_command`, `apply_edits` <=5 files + `bestEffort` >=3
  files, and Swarm `--cli` syntax card).
- `templates/antigravity/swarm-code-worker-brief.md` — bundled progressive-disclosure
  Skill materialized into `~/.gemini/config/skills/swarm-code-worker-brief/SKILL.md`.

Personal credentials, private repository maps, private GitHub owner rules, and
machine-specific overlays remain user-owned and outside Flow's public templates.

## Direct Commands

Inspect the effective AntiGravity environment (plugins, rules, budgets, skills,
duplicate checks, and recent local telemetry):

```bash
python3 scripts/opl_workflow.py antigravity doctor --json
```

Preview planned changes without writing any file:

```bash
python3 scripts/opl_workflow.py antigravity apply --dry-run --json
```

Apply the safe AntiGravity template baseline (backs up modified files under
`~/.gemini/.opl-flow-backups/<timestamp>/`, updates only managed marker blocks,
preserves all user content outside markers, and refuses to duplicate overlapping
unmarked headings):

```bash
python3 scripts/opl_workflow.py antigravity apply --json
```

Install the recommended `agy-fast` plugin through its official owner installer
when absent, then materialize overrides and skills:

```bash
python3 scripts/opl_workflow.py antigravity apply --install-plugins --json
```

Optionally install the read-only weekly environment audit automation (strictly
opt-in, never auto-enabled in `config.json`; user enables it manually in
AntiGravity Automations):

```bash
python3 scripts/opl_workflow.py antigravity apply --with-weekly-audit --tz Asia/Shanghai --json
```

## Safety Boundaries

- Never overwrite an existing unmarked `GEMINI.md` or `AGENTS.local.md` with
  overlapping sections; when `sync_status` is `merge_required`, review and merge
  semantically while preserving every user preference.
- Never auto-enable scheduled automations in `~/.gemini/config/config.json` or
  grant wildcard tool permissions (`command(*)`, `read_file(*)`, `write_file(*)`).
- Never uninstall or disable user plugins automatically; report unused or
  duplicate entries and let the user decide.
