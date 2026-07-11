---
name: "opl-flow"
description: "Use when installing, syncing, diagnosing, or explaining the OPL Flow workflow profile, or when the user explicitly asks to use OPL Flow. Normal development work should follow the active AGENTS profile and load only the relevant specialist skill."
---

# OPL Flow

OPL Flow distributes the user's Codex workflow profile. It is compatible with One Person Lab App Full installs, but owns the Workflow Profile layer only: the user-level `AGENTS.md` runtime profile, non-runtime `TASTE.md` authoring source, explicit planner/executor/debugger/verifier compatibility prompts, the `opl-flow` plugin, and the fail-closed `codex-ops-kit` Git/release guardrail.

Keep project facts, runtime truth, release authority, domain verdicts, and owner receipts in their existing repo or runtime surfaces. Risk-aware evidence selection is part of `AGENTS.md`; do not create a separate prose router for it.

## Route

- Use this skill for profile installation, update, sync, merge diagnostics, compatibility checks, CodexCont control, or OPL Flow explanation.
- For ordinary repo work, follow the active `AGENTS.md` and repo-native facts. Do not load TASTE or the four compatibility prompts unless the user explicitly asks for them.
- Use `codex-ops-kit` only for Git worktree/branch lifecycle events and public GitHub release/install claims.
- Use available specialist skills for systematic debugging, TDD, verification, documents, browsers, and domain workflows.
- Treat One Person Lab App runtime, capability-package health, GUI state, and Full readiness as App/Framework authority, not OPL Flow readiness.

## Install And Verify

Run from the repository checkout:

```bash
python3 scripts/install_local_plugin.py
python3 scripts/check_companion_skills.py --strict
python3 scripts/install_local_plugin.py --verify-only
```

The installer stages `~/plugins/opl-flow`, installs the exact `opl-flow@opl-flow-local` plugin, refreshes the versioned Codex cache, and verifies marketplace, plugin, cache, profile, and runtime-discoverable `codex-ops-kit` readback. Use `--no-profile` when only the plugin payload should change.

The installed surfaces have different authority:

- Runtime profile and readiness gate: `~/.codex/AGENTS.md`
- Non-runtime authoring source: `~/.codex/TASTE.md`
- Explicit compatibility prompts: `~/.codex/prompts/{planner,executor,debugger,verifier}.md`

Existing user `AGENTS.md` content requires semantic merge; a normal install returns nonzero with a packet instead of reporting terminal success. `output/AGENTS.md` and `output/merge-report.md` are required; TASTE and prompt outputs are optional. Apply the reviewed packet with:

```bash
python3 scripts/install_local_plugin.py --apply-merge-packet <packet-path>
```

The apply command backs up current targets and records the approved source/target receipt. Restart Codex after installation so plugin and skill discovery refresh.

## Optional Companions

Preserve the current local Superpowers profile unless the user explicitly requests another one. OPL Flow routes to installed specialist skills; it does not vendor or replace them.

Ponytail is compatible as an optional simplification lens with workstation default `lite`. The Codex hook profile should inject only a 5-10 line delta once at root startup, never on resume/compact/subagent. Route Ponytail by surface: use `ponytail-audit` for broad cleanup discovery and `ponytail-review` for concrete diffs or lanes. It cannot weaken scope, authority, fresh evidence, runtime/currentness, or completion-audit requirements.

## Repo Profile Sync

```bash
python3 scripts/repo_profile.py check --repo-root <repo-root>
python3 scripts/repo_profile.py sync --repo-root <repo-root>
python3 scripts/repo_profile.py sync --repo-root <repo-root> --apply
```

`sync` is dry-run unless `--apply` is provided. Apply mode may update the OPL Flow managed block and profile contract, while preserving repo-specific guidance outside that block.

## Intelligence Enhancement

Use the OPL Flow-owned CodexCont entrypoint:

```bash
python3 scripts/intelligence_enhancement.py enable --bootstrap-opl
python3 scripts/intelligence_enhancement.py status
python3 scripts/intelligence_enhancement.py repair
python3 scripts/intelligence_enhancement.py disable
```

Use `uninstall --confirmation uninstall_codexcont` only for an explicit uninstall request. `status` proves current local configuration and service readback, not absolute always-online behavior.

## Readback Boundary

`check_companion_skills.py` reports the AGENTS runtime profile, non-blocking authoring/compatibility surface drift, exact plugin/cache, `codex-ops-kit`, Superpowers profile, and optional Ponytail state. Default mode is diagnostic; `--strict` fails closed unless the runtime profile, exact installed plugin/cache payload, and runtime guardrail are current.

Do not use docs, staged files, source checkouts, focused tests, or plugin candidates alone to claim runtime, release, currentness, or owner acceptance.
