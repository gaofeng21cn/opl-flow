---
name: "opl-flow"
description: "Use when installing, syncing, diagnosing, or explaining the OPL Flow workflow profile, or when the user explicitly asks to use OPL Flow. OPL Flow keeps normal development model-native and does not bootstrap a development methodology."
---

# OPL Flow

OPL Flow distributes the user's minimal Codex preference profile. It owns the user-level `AGENTS.md`, non-runtime `TASTE.md`, plugin payload semantics, workflow policy, and model recommendation.

Keep project facts and development procedures out of the user-level profile. Repo-local instructions, contracts, source, tests, and runtime surfaces remain authoritative for the project.

## Route

- Use this skill for OPL Flow profile explanation, repository-local profile sync, or diagnosis of its package-delivered profile and plugin payload.
- Use `$coordinate-concurrent-tasks` for multi-thread ownership, parallel execution, fresh-SSOT integration, task-gap auditing, and archive-readiness review. It coordinates existing authorities; it does not grant Git, release, package, or thread-archive permission.
- For ordinary repo work, follow the active `AGENTS.md` and repo-native facts.
- Let the model handle ordinary design and development directly.

## Install And Verify

For normal installation and update, use the OPL Framework package lifecycle:

```bash
opl packages install opl-flow
opl packages update opl-flow
opl packages optimize opl-flow
```

The package lifecycle owns dependency resolution, conflict retirement, install, update, optimize, rollback, Codex configuration, receipts, and package currentness. Explicit install, update, or optimize authorizes the policy migration in `contracts/workflow-policy.json`; use the command's keep override only for intentionally retained conflicts. `scripts/install_local_plugin.py` is only a repository developer/local-source tool for staging and verifying a checkout; it is not the normal user installer or package authority.

The installed surfaces have different authority:

- Runtime profile: `~/.codex/AGENTS.md`
- Non-runtime authoring source: `~/.codex/TASTE.md`

Existing user `AGENTS.md` content is merged semantically by Codex inside the package transaction. Scripts remove only known marker blocks. If Codex cannot produce a valid merge, follow the review/apply fallback route returned by the package command. Restart Codex after installation so plugin and skill discovery refresh.

OPL Flow declares dependencies and incompatibilities; OPL Framework executes them. Entries under `recommends` with `online_install_default=true` are managed dependencies, not advisory text: Framework installs and updates them with OPL Flow, and App Full bundles the same `offline_bundle=full` closure. OPL App may present user overrides, but it must not maintain a second skill list or model policy.

After any App carrier changes version, App requests generic Framework reconciliation for OPL Base and all installed OPL Packages. If OPL Flow is installed, the ordinary package update transaction refreshes its dependency closure, retires declared conflicts, and reconciles the user profile. OPL Flow does not provide an App-specific updater.

While App is running, generic reconciliation runs after startup readiness and every 24 hours. OPL Packages refreshes Flow-managed Skills; OPL Base owns managed CLI currentness and updates. Managed Codex and Framework/Temporal generations activate on the next App process. External Homebrew, npm, PATH, or system installations are never silently overwritten; a verified original owner may be invoked only after explicit user confirmation, otherwise the App shows guidance.

In Settings, Agents owns runnable Agent packages, Capabilities groups Flow-managed and manual/third-party Skills or Plugins, and Local Environment owns Base/App/Packages plus dependency currentness. Treat those surfaces as consumers of Framework readback, not additional lifecycle owners.

## Repo Profile Sync

```bash
python3 scripts/repo_profile.py check --repo-root <repo-root>
python3 scripts/repo_profile.py sync --repo-root <repo-root>
python3 scripts/repo_profile.py sync --repo-root <repo-root> --apply
```

`sync` is dry-run unless `--apply` is provided. Apply mode updates only the profile contract and removes any legacy OPL Flow managed block from `AGENTS.md`. Repo-local instructions remain entirely repository-owned; OPL Flow does not inject workflow prose into them.

## Readback Boundary

Keep these currentness layers separate:

1. Owner source: the OPL Flow repository commit and release tag.
2. Framework catalog: the selected stable Package version and payload manifest.
3. Installed projection: the package lock, installed payload digest, managed-Skill validation, and resolved entrypoint authority.
4. Codex discovery: the plugin version returned by a fresh `codex plugin list --json` process.

An owner tag or catalog entry does not prove that this machine has switched. Package currentness requires installed-lock and payload readback; active discovery additionally requires the fresh Codex readback. For managed Skills, Framework must prefer the declared Skills Manager authority, validate the final frontmatter and referenced-resource closure, ignore runtime bytecode caches when hashing, and converge Codex and Agents entrypoints on the same physical source.

For repository development, `install_local_plugin.py --verify-only` checks the AGENTS profile, exact staged plugin, installed plugin identity, and versioned cache payload. It does not replace Framework package currentness or fresh Codex discovery.
