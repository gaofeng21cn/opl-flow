# OPL Flow New Machine Setup

Owner: `gaofeng`
Purpose: `new_machine_opl_flow_profile_setup`
State: `active`
Machine boundary: Human-readable setup runbook. Package installation, profile
migration, installed currentness, and active discovery remain in Framework package
transactions, receipts, package readback, and fresh Codex discovery output.

This page installs the OPL Flow preference profile only. For the complete OPL family setup, use the canonical [One Person Lab bootstrap guide](https://github.com/gaofeng21cn/one-person-lab/blob/main/docs/references/current-support/opl-new-machine-codex-bootstrap.md).

## Install

```bash
opl packages install opl-flow
opl packages update opl-flow
opl packages optimize opl-flow
```

OPL Flow installs:

- the minimal user-level `~/.codex/AGENTS.md` preference profile;
- the non-runtime `~/.codex/TASTE.md` authoring source;
- the normal package plugin identity `opl-flow@opl-agent-opl-flow-local`;

The default plugin exposes only the `opl-flow` skill. `codex-ops-kit` remains an optional source under `optional-skills/`; it is installed only when explicitly selected and is never a profile readiness dependency.

The Framework package transaction applies the policy's declared conflict migration: matching legacy workflow surfaces are backed up, removed from active discovery and recorded in a rollback receipt. A migration id can be retained explicitly with `--keep`.

The same transaction resolves `contracts/workflow-policy.json`. Every `recommends` entry with `online_install_default=true` is a managed dependency: Framework installs and updates it with OPL Flow, applies the model recommendation without overriding a user-pinned model, and writes a rollback receipt. App Full bundles the same entries marked `offline_bundle=full` for offline installation; it does not keep a separate skill or tool list.

If `~/.codex/AGENTS.md` already exists, the package lifecycle backs it up and asks Codex to merge the minimal profile with distinct user preferences. Known marker blocks are removed deterministically; unmarked prose is never rewritten by a heuristic script. A target-hash check precedes apply. If Codex cannot complete a valid merge, the original file remains unchanged and the package command returns the review/apply route for its merge packet.

Restart Codex after installation so plugin and skill discovery refresh.

After any App carrier changes version, the App asks Framework to reconcile OPL Base and every installed OPL Package. An installed OPL Flow therefore receives the same dependency refresh, conflict retirement, and profile migration as an explicit package update. Package payload changes apply immediately, with a Codex restart required only to refresh plugin and skill discovery; Base runtime changes follow the Framework staging and restart-activation policy.

The same generic reconciliation runs after App startup readiness and every 24 hours while App remains open. Flow-managed Skills update through OPL Packages. Managed OfficeCLI and MinerU CLI currentness belongs to OPL Base. Managed Codex and Framework/Temporal generations switch on the next App process. External Homebrew, global npm, PATH, or system-owned Codex/Temporal installations are detect-only during background maintenance; when the original owner is verified, Settings may offer an explicitly confirmed owner update, otherwise it shows manual guidance.

Settings separates the objects by owner: Agents for runnable Agent packages, Capabilities for OPL Flow-managed and manual/third-party Skills or Plugins, and Local Environment for OPL Base, OPL App, OPL Packages, and dependency status.

## Development Repositories

The installed global profile tells Codex to initialize CodeGraph when entering a development repository that lacks an index:

```bash
codegraph init .
```

The repository must Git-ignore `.codegraph/` and keep a concise repo-local CodeGraph block in `AGENTS.md`. Structural searches should use CodeGraph; literal text searches should use `rg`.

## Verification Boundary

For repository development only, `scripts/install_local_plugin.py --verify-only` checks a locally staged checkout and exact plugin/cache payload. It is not a package-currentness claim.
