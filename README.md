# OPL Flow

OPL Flow is a lightweight Codex workflow profile for pragmatic local engineering. It packages the workflow now used on this workstation into a reusable Codex plugin and installable user profile.

It is inspired by Trellis and Superpowers, but stays Codex-first:

- Direct / Inline / Durable task tiers.
- Planner / Executor / Debugger / Verifier role prompts.
- Codex inline execution by default.
- Subagent dispatch contract for scoped parallel work.
- Durable evidence and lesson writeback.
- Verification before completion.
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

Restart Codex after installation.

For a complete new-machine setup that installs the OPL runtime, One Person Lab App, MAS/MAG/RCA/OMA agent surfaces, OPL Flow, OPL Doc, and companion tools, use the [One Person Lab new-machine Codex bootstrap guide](https://github.com/gaofeng21cn/one-person-lab/blob/main/docs/references/current-support/opl-new-machine-codex-bootstrap.md).

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
python3 scripts/verify.py
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

The profile reads preferences by scope: repo-local `TASTE.md` first, then `~/.codex/TASTE.md` when no repo-local file exists. `TASTE.md` never overrides code, contracts, docs, runtime output, or direct user instructions.

## Relationship To OPL Doc

OPL Flow is the generic workflow layer. OPL Doc is the domain skill that governs OPL-family developer documentation lifecycle. The older `opl-doc-governance` skill name is only a compatibility entry. OPL Doc can use OPL Flow's Durable writeback, subagent contract, and verifier gates, but the two should stay separate.

For plugin-native repos, OPL Flow owns the workflow managed block while OPL Doc
owns documentation lifecycle profile checks. The shared machine pointer is
`contracts/opl-native-profile.json`.

## Development

```bash
python3 scripts/verify.py
python3 /Users/gaofeng/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .
```
