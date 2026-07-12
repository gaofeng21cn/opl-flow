---
name: "opl-flow"
description: "Use when installing, syncing, diagnosing, or explaining the OPL Flow workflow profile, or when the user explicitly asks to use OPL Flow. OPL Flow keeps normal development model-native and does not bootstrap a development methodology."
---

# OPL Flow

OPL Flow distributes the user's minimal Codex preference profile. It owns the user-level `AGENTS.md`, non-runtime `TASTE.md`, plugin payload, and installation/readback contract.

Keep project facts and development procedures out of the user-level profile. Repo-local instructions, contracts, source, tests, and runtime surfaces remain authoritative for the project.

## Route

- Use this skill for OPL Flow profile explanation, repository-local profile sync, or diagnosis of its package-delivered profile and plugin payload.
- For ordinary repo work, follow the active `AGENTS.md` and repo-native facts.
- Let the model handle ordinary design and development directly.

## Install And Verify

For normal installation and update, use the OPL Framework package lifecycle:

```bash
opl packages install opl-flow
opl packages update opl-flow
```

The package lifecycle owns install, update, rollback, and package currentness. `scripts/install_local_plugin.py` is only a repository developer/local-source tool for staging and verifying a checkout; it is not the normal user installer or package authority.

The installed surfaces have different authority:

- Runtime profile: `~/.codex/AGENTS.md`
- Non-runtime authoring source: `~/.codex/TASTE.md`

Existing user `AGENTS.md` content requires semantic merge. Follow the review/apply route returned by the package command; restart Codex after installation so plugin and skill discovery refresh.

## Repo Profile Sync

```bash
python3 scripts/repo_profile.py check --repo-root <repo-root>
python3 scripts/repo_profile.py sync --repo-root <repo-root>
python3 scripts/repo_profile.py sync --repo-root <repo-root> --apply
```

`sync` is dry-run unless `--apply` is provided. Apply mode may update the OPL Flow managed block and profile contract, while preserving repo-specific guidance outside that block.

## Optional Intelligence Enhancement

OPL Flow may declare optional CodexCont-style continuation intent. OPL Base/System and Managed Update own dependency installation, Codex configuration, launchd/systemd/container service lifecycle, status, repair, rollback, and removal. Do not operate that lifecycle from this repository.

## Readback Boundary

For repository development, `install_local_plugin.py --verify-only` checks the AGENTS profile, exact staged plugin, installed plugin identity, and versioned cache payload. Package lifecycle currentness remains with OPL Framework.
