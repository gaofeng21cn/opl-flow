# OPL Flow New Machine Setup

Owner: `gaofeng`
Purpose: `new_machine_opl_flow_profile_setup`
State: `active`

This page installs the OPL Flow preference profile only. For the complete OPL family setup, use the canonical [One Person Lab bootstrap guide](https://github.com/gaofeng21cn/one-person-lab/blob/main/docs/references/current-support/opl-new-machine-codex-bootstrap.md).

## Install

```bash
opl packages install opl-flow
opl packages update opl-flow
```

OPL Flow installs:

- the minimal user-level `~/.codex/AGENTS.md` preference profile;
- the non-runtime `~/.codex/TASTE.md` authoring source;
- the exact `opl-flow@opl-flow-local` plugin payload;
- the optional `codex-ops-kit` utility, discoverable only for explicit lane or public-release audit requests.

It does not install task tiers, planner/executor/debugger/verifier prompts, a development methodology, a startup coding persona, Superpowers, or Ponytail. OPL App does not package or auto-install Superpowers.

If `~/.codex/AGENTS.md` already exists, the package lifecycle does not overwrite it. It creates a merge packet and returns the review/apply route. OPL Framework remains the install, update, rollback, and package-currentness owner.

Restart Codex after installation so plugin and skill discovery refresh.

## Development Repositories

The installed global profile tells Codex to initialize CodeGraph when entering a development repository that lacks an index:

```bash
codegraph init .
```

The repository must Git-ignore `.codegraph/` and keep a concise repo-local CodeGraph block in `AGENTS.md`. Structural searches should use CodeGraph; literal text searches should use `rg`.

## Optional Intelligence Enhancement

OPL Flow can declare optional CodexCont-style continuation intent. OPL Base/System and Managed Update own dependency installation, Codex configuration, service lifecycle, status, repair, rollback, and removal. OPL Flow provides no independent companion updater or readiness checker.

## Verification Boundary

For repository development only, `scripts/install_local_plugin.py --verify-only` checks a locally staged checkout and exact plugin/cache payload. It is not a package-currentness claim.
