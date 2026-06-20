# OPL Flow

OPL Flow is a lightweight Codex workflow profile for pragmatic local engineering. It packages the workflow now used on this workstation into a reusable Codex plugin and installable user profile.

It is inspired by Trellis and Superpowers, but stays Codex-first:

- Direct / Inline / Durable task tiers.
- Planner / Executor / Debugger / Verifier role prompts.
- Bundled risk-based development flow for verification budget, test additions, TDD selection, and completion evidence.
- Bundled high-risk Codex ops routing into `codex-ops-kit` for worktree/subagent lanes, RHO/session-history audit, manifest drift, release/currentness claims, secret/cache freshness, and long evidence chains.
- Codex inline execution by default.
- Subagent/worktree lane contract for scoped parallel work.
- Durable evidence and lesson writeback.
- Verification before completion, including Chinese "完成度审计" for target-state delivery.
- Fresh evidence boundaries for runtime truth, readiness, currentness, release, CI, and owner-route claims.
- CodeGraph marker block preservation for projects that rely on CodeGraph injection.
- RTK shell preference for compact command output when available.
- Repo-local workflow profile check/sync for OPL-native development directories.

## Install On A New Machine

```bash
git clone https://github.com/gaofeng21cn/opl-flow.git
cd opl-flow
python3 scripts/install_local_plugin.py
```

This installs:

- local plugin: `~/plugins/opl-flow`
- personal marketplace entry: `~/.agents/plugins/marketplace.json`
- Codex workflow profile:
  - `~/.codex/AGENTS.md`
  - `~/.codex/TASTE.md`
  - `~/.codex/prompts/planner.md`
  - `~/.codex/prompts/executor.md`
  - `~/.codex/prompts/debugger.md`
  - `~/.codex/prompts/verifier.md`

Existing user profile files are backed up before replacement unless their content already matches the template.

`TASTE.md` carries default maintenance preferences. A repo-local `TASTE.md` remains stronger for that repo; the user-level file is the fallback when a target repo has no local taste document.

The profile routes to companion skills by name. OPL Flow bundles the profile-native guardrails `risk-based-development-flow` and `codex-ops-kit` so a fresh install raises Codex's behavioral floor without a separate local skill copy. OPL App Full installs the Superpowers execution surface and common companion skills, so it normally satisfies `systematic-debugging`, `verification-before-completion`, `using-git-worktrees`, `test-driven-development`, `mineru-document-extractor`, PDF, OfficeCLI, and UI/UX helper coverage. OPL Flow preserves the current local Superpowers profile by default; switching to official full Superpowers is an explicit user choice, not an installer side effect. `agent-browser`, RTK, and CodeGraph remain optional machine-level enhancements.

Check a machine with:

```bash
python3 scripts/check_companion_skills.py
```

The checker reports both the Superpowers bundle readiness and the active local Superpowers profile (`lite`, `expanded`, `full`, `custom`, or `not_configured`). `lite` and `expanded` keep the local routing profile and leave upstream `using-superpowers` disabled; `full` links the complete upstream skills directory and enables the official bootstrap.

Use strict mode when checking that the OPL Flow-owned guardrail payload is discoverable:

```bash
python3 scripts/check_companion_skills.py --strict
```

Restart Codex after installation.

For a complete new-machine setup that installs the OPL runtime, One Person Lab App, MAS/MAG/RCA/OMA agent surfaces, OPL Flow, OPL Doc, and companion tools, use the [One Person Lab new-machine Codex bootstrap guide](https://github.com/gaofeng21cn/one-person-lab/blob/main/docs/references/current-support/opl-new-machine-codex-bootstrap.md). BookForge is tracked as a new OPL-standard repo, but default Connect/App visibility needs separate admission evidence.

You can paste this into Codex on the new machine:

```text
Please follow the official One Person Lab new-machine guide and set up this machine with the OPL agent runtime environment and the complete Codex workflow toolkit.
Source of truth: https://github.com/gaofeng21cn/one-person-lab/blob/main/docs/references/current-support/opl-new-machine-codex-bootstrap.md
```

## Install Plugin Only

```bash
python3 scripts/install_local_plugin.py --no-profile
```

## Verify

```bash
python3 scripts/install_local_plugin.py --verify-only
scripts/verify.sh
```

## Repo Profile Sync

OPL Flow can check or write the workflow portion of an OPL-native repo profile:

```bash
python3 scripts/repo_profile.py check --repo-root /path/to/repo
python3 scripts/repo_profile.py sync --repo-root /path/to/repo
python3 scripts/repo_profile.py sync --repo-root /path/to/repo --apply
```

`sync` is a dry-run unless `--apply` is present. Apply mode preserves
repo-specific prose and only updates `contracts/opl-native-profile.json` plus
managed blocks in `AGENTS.md` and `TASTE.md`. Those managed blocks point to the
profile and do not own contracts, source, tests, runtime output, or project
truth.

## Usage

Ask Codex:

```text
Use OPL Flow for this task.
```

The profile routes work by shape:

- Direct: answer directly with minimal reads.
- Inline: main session implements and verifies.
- Durable: persist plan, evidence, decision, or runbook in the right file.

It also routes evidence-sensitive work:

- Risk-based verification: classify the risk, choose a verification budget, and avoid TDD/test bloat unless it proves a concrete regression.
- High-risk Codex ops: use `codex-ops-kit` before lane start/absorb/closeout, broad manifest drift, RHO/session-history audits, release/currentness claims, generated/runtime config drift, secret/cache freshness, or long evidence chains.
- Completion audits: for "全部落地 / 一步到位 / 彻底解决" style goals, verify against the original target plan and report Chinese "完成度审计" with status, percent, fresh evidence, gaps, and next actions.

The profile reads preferences by scope: repo-local `TASTE.md` first, then `~/.codex/TASTE.md` when no repo-local file exists. `TASTE.md` never overrides code, contracts, docs, runtime output, or direct user instructions.

## Compatibility With OPL App Full

OPL Flow is compatible with the One Person Lab App Full first-install payload. Treat the layers separately:

- OPL App Full packages Superpowers and common companion skills.
- OPL Flow installs the user-level workflow profile, the `opl-flow` plugin, and the OPL Flow-owned guardrails `risk-based-development-flow` and `codex-ops-kit`.
- OPL Flow should not overwrite user-owned `AGENTS.md` without backup, and OPL App session context should respect existing user profile files.
- Superpowers should remain the execution surface for its official skills; OPL Flow only routes to the active local profile. On this workflow, `lite` is the quiet default, `expanded` exposes v6 planning / SDD / review skills for long-chain implementation, and `full` is reserved for explicit official Superpowers use.
- OPL Flow does not own OPL App/runtime readiness. Temporal family runtime provider, native helpers, domain module health, GUI shell, App first-run state, and Full readiness belong to One Person Lab App / OPL Framework surfaces and should be checked there, not treated as OPL Flow profile gaps.

See [docs/compatibility.md](docs/compatibility.md) for the positioning matrix against Codex customization, Superpowers, Trellis, Claude Code skills/subagents/memory, and GitHub Agentic Workflows.

## Relationship To OPL Doc

OPL Flow is the generic workflow layer. OPL Doc is the domain skill that governs OPL-family developer documentation lifecycle. OPL Doc can use OPL Flow's Durable writeback, subagent contract, and verifier gates, but the two should stay separate.

For plugin-native repos, OPL Flow owns the workflow managed block while OPL Doc
owns documentation lifecycle profile checks. The shared machine pointer is
`contracts/opl-native-profile.json`.

`opl-flow` itself is the source repository for that profile and is intentionally
self-hosted without a repo-local `contracts/opl-native-profile.json`, `AGENTS.md`,
or `TASTE.md`. Run `repo_profile.py check` against consumer OPL-native repos, not
as a self-check for this repository.

## Development

```bash
scripts/verify.sh
python3 /Users/gaofeng/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .
```
