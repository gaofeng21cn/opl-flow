---
name: "opl-flow"
description: "Use when installing, syncing, diagnosing, or explaining the OPL Flow workflow profile, or when the user explicitly asks to use OPL Flow. OPL Flow keeps normal development model-native and does not bootstrap a development methodology."
---

# OPL Flow

OPL Flow is an optional `OPL Package(kind=workflow_profile)` that distributes
the user's minimal Codex preference profile. It owns the Profile source and
intent, not OPL Base/App readiness, Package currentness, project facts,
runtime/domain truth, or another executor.

Keep project facts and procedures repo-local. Let the model handle ordinary
design and development directly.

## Route

- Use this skill to install, update, sync, explain, or diagnose the minimal
  Profile.
- Use `$coordinate-concurrent-tasks` only for bounded multi-task ownership,
  parallel execution, fresh-SSOT integration, and archive-readiness review.
- Follow effective repo-local `AGENTS.md`, contracts, source, tests, and fresh
  readback for ordinary repository work.
- Do not make Flow a prerequisite for Base, App, Standard, Full, plain Codex,
  another Package, or domain readiness.

## Package, Publication, Carrier, Executor

Keep the three runtime layers separate and treat publication as an independent
axis:

```text
Package     = opl-flow identity and capabilities
Publication = owner source/tag and official GHCR bytes/current alias
Carrier     = local install/update/remove and fresh installed readback
Executor    = discovery and execution route for installed capabilities
```

GHCR is a publication store/source, not a carrier. Codex Plugin Manager and
Codex CLI are the only formal carrier/executor production path today. Keep
Package identity, Profile, preferences, tasks, and public status/actions
OPL-owned so a future executor adapter can change without reinstalling Flow.
A minimal Git/local neutral adapter proof may verify that boundary; it is not a
second supported carrier or executor product.

Normal dependencies are stable identity presence/callability. Do not require
SemVer/ABI resolution, lock, payload, receipt, digest, provenance, or a shared
release cohort. Breaking interfaces use a new identity or owner-side adapter.

## Install And Verify

Use the currently executable Framework compatibility route:

```bash
opl packages install opl-flow
opl packages update opl-flow
opl packages optimize opl-flow
```

The current implementation may still return resolver, lock, payload, receipt,
rollback, or provenance fields. Treat those as transitional implementation
readback, not target composition gates.

Existing compatibility code may describe dependency selection as an
`available compatible source`. Read that phrase as the current adapter route;
the target only needs identity presence/callability and does not add a central
version or provenance solver.

The target official online source is the Flow owner's per-Package GHCR
`opl-flow:latest-stable`. The shared `one-person-lab-manifest:latest-stable`
serves only Full/offline/integration-test/QA snapshots. GHCR does not install
the Package or define local truth. A thin Base OCI adapter may download, verify,
and hand off bytes; the configured carrier performs install/update/remove and
fresh readback. Codex owns Plugin/config/cache, while the complete Flow Package
still needs carrier installed readback.

`scripts/install_local_plugin.py` is only a repository developer/local-source
tool. It is not ordinary installation or Package currentness authority.

## Profile Safety

Installed user surfaces:

- Runtime profile: `~/.codex/AGENTS.md`
- Non-runtime authoring source: `~/.codex/TASTE.md`

For an existing `AGENTS.md`, preserve these invariants:

1. hash the original target;
2. back it up before mutation;
3. remove only known marker blocks and preserve distinct preferences;
4. compare the target SHA immediately before apply;
5. validate and atomically replace, otherwise leave the original untouched.

If semantic merge cannot be validated, follow the review/apply fallback route returned by the package command.
Current compatibility implementations may use a merge packet and rollback
receipt. Do not generalize that Profile-specific safety into a Package
lock/payload/receipt requirement.

Restart the selected executor when its discovery requires refresh.

## App Boundary

Flow can be a default root in the single App Official Profile, but the Profile
runs only at first install or explicit Restore. Standard installs online; Full
may use an offline seed. If the user uninstalls Flow, startup, daily maintenance,
and App updates must not reinstall it.

OPL App must not parse Flow's companion Skill/Tool/Plugin/MCP list or keep a
second model inventory. It consumes only Framework's generic projection of
actual carrier state. Missing Flow or a dependency is local to Flow.

Use model precedence:

```text
explicit user selection
> installed Flow recommendation
> fresh executor default
> App fallback when Flow is unavailable
```

Never bundle credentials or overwrite unknown user/third-party MCP
configuration.

## Repo Profile Sync

```bash
python3 scripts/repo_profile.py check --repo-root <repo-root>
python3 scripts/repo_profile.py sync --repo-root <repo-root>
python3 scripts/repo_profile.py sync --repo-root <repo-root> --apply
```

`sync` is dry-run unless `--apply` is provided. Apply mode updates only the
profile contract and removes known legacy Flow marker blocks. Repo-local
instructions remain entirely repository-owned.

## Readback Boundary

Read these independently:

1. owner source/tag and per-Package GHCR `latest-stable`;
2. complete Package installed/healthy state from the local carrier;
3. selected executor discovery and callability;
4. exact Full/QA snapshot when that build is in scope.

During migration, the compatibility checks are:

```bash
opl packages list --json
opl packages status --package-id opl-flow --json
codex plugin list --json
```

An owner tag, shared manifest, Framework lock, Plugin payload, docs, or tests
cannot prove all four layers. `install_local_plugin.py --verify-only` proves
only the local Codex development carrier.

The target boundary and current migration gap are documented in
`docs/capability-governance.md` and `docs/status.md`. Do not claim migration
complete until actual install/update/remove, Standard/Full, Profile safety,
complete Package, the formal Codex route, and the bounded Git/local neutral
contract proof all pass. Do not build or imply a second executor product merely
to satisfy that proof.
