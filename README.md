# OPL Flow

OPL Flow is a lightweight Codex workflow profile for pragmatic local engineering. It packages the workflow now used on this workstation into a reusable Codex plugin and installable user profile.

It is inspired by Trellis and Superpowers, but stays Codex-first:

- Direct / Inline / Durable task tiers.
- Planner / Executor / Debugger / Verifier role prompts.
- Codex inline execution by default.
- Subagent dispatch contract for scoped parallel work.
- Durable evidence and lesson writeback.
- Verification before completion.

## Install On A New Machine

```bash
git clone git@github.com:gaofeng21cn/opl-flow.git
cd opl-flow
python3 scripts/install_local_plugin.py
```

This installs:

- local plugin: `~/plugins/opl-flow`
- personal marketplace entry: `~/.agents/plugins/marketplace.json`
- Codex workflow profile:
  - `~/.codex/AGENTS.md`
  - `~/.codex/prompts/planner.md`
  - `~/.codex/prompts/executor.md`
  - `~/.codex/prompts/debugger.md`
  - `~/.codex/prompts/verifier.md`

Existing user profile files are backed up before replacement unless their content already matches the template.

Restart Codex after installation.

## Install Plugin Only

```bash
python3 scripts/install_local_plugin.py --no-profile
```

## Verify

```bash
python3 scripts/install_local_plugin.py --verify-only
python3 scripts/verify.py
```

## Usage

Ask Codex:

```text
Use OPL Flow for this task.
```

The profile routes work by shape:

- Direct: answer directly with minimal reads.
- Inline: main session implements and verifies.
- Durable: persist plan, evidence, decision, or runbook in the right file.

## Relationship To OPL Doc

OPL Flow is the generic workflow layer. OPL Doc Governance is a domain skill that governs OPL-family developer documentation lifecycle. OPL Doc can use OPL Flow's Durable writeback, subagent contract, and verifier gates, but the two should stay separate.

## Development

```bash
python3 scripts/verify.py
python3 /Users/gaofeng/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .
```
