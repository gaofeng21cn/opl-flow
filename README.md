# OPL Flow

OPL Flow distributes a minimal Codex preference profile. It keeps ordinary design and development model-native and adds only concise CodeGraph bootstrap guidance for development repositories.

## Public Role Boundary

OPL Flow owns the user-level `AGENTS.md` profile and its installation/readback contract. The plugin also carries `codex-ops-kit` as an explicitly invoked utility; it is not a profile dependency or readiness signal.

OPL Flow is not runtime truth, package truth, or domain truth. It does not own
OPL App readiness, OPL Framework runtime behavior, OPL Packages lifecycle,
release currentness, companion-tool health, project facts, source behavior, or
domain acceptance. Those claims stay with the owning App, Framework, package,
repo, runtime, contract, test, or owner-receipt surface.

It stays Codex-first:

- Chinese, conclusion-first, concise communication preferences.
- Read the effective project location, call path, repo-local instructions, contracts, and implementation before editing.
- RTK as a compact shell default, with native commands allowed when fidelity matters.
- Initialize `.codegraph/` in development repositories, keep it Git-ignored, and add a concise repo-local CodeGraph block.

## User Profile Source

`templates/AGENTS.md` is rendered from one flat source module,
`profile/modules/01-user-preferences.md`, declared by `profile/manifest.json`.
The single-module shape is intentional: the profile is too small to benefit
from section or module routing.

Regenerate and check the rendered profile with:

```bash
python3 scripts/profile_compose.py write
python3 scripts/profile_compose.py check
```

The composer only performs deterministic module rendering. The Framework package
transaction asks Codex to reconcile an existing user-level `AGENTS.md`
semantically; scripts only remove policy-declared marker blocks and never guess
at unmarked user preferences.

## Install Or Update

```bash
opl packages install opl-flow
opl packages update opl-flow
opl packages optimize opl-flow
```

The OPL Framework package lifecycle owns installation, update, rollback, and package currentness. It installs:

- the managed OPL Flow plugin payload and Codex discovery entry
- Runtime workflow profile: `~/.codex/AGENTS.md`
- Non-runtime authoring source: `~/.codex/TASTE.md`

On a machine without `~/.codex/AGENTS.md`, the package lifecycle writes the rendered OPL
Flow profile directly. On a machine that already has user-level `AGENTS.md`, the same
transaction backs up the file, removes only known marker-delimited legacy blocks, and
uses Codex to merge distinct user preferences into the minimal candidate. The result is
validated against the candidate baseline and the original target hash before atomic
apply. Conflict retirement and profile changes share one rollback receipt.

If Codex is unavailable, its output fails validation, or the target changes during the
transaction, the original file remains in place and a reviewable merge packet is kept
under the Framework state directory. The command returns the exact
`opl packages profile-apply opl-flow --packet <path>` fallback route.

`~/.codex/TASTE.md` is the human-maintained preference authoring source, not a session input. Its stable digest is compiled into `AGENTS.md`; its absence or drift does not fail runtime readiness. Repo-specific facts, local boundaries, and project development rules belong in `AGENTS.md`, docs, contracts, source, tests, and runtime/readback evidence.

Installing, updating, or optimizing OPL Flow applies the manifest migration policy and records every archived legacy surface in a rollback receipt. Explicit `--keep` overrides are preserved in the same package transaction. `optimize` reuses the installed source without pulling it for an explicit local-only reconciliation. After any App carrier changes version, OPL App requests generic Framework reconciliation for OPL Base and every installed OPL Package. If OPL Flow is installed, its ordinary package transaction refreshes the managed source and dependency closure before applying conflict retirement and profile migration; there is no Flow-specific App updater.

Use the package command's readback for installed version and package currentness. OPL Flow does not maintain a second companion or readiness checker.

Restart Codex after installation.

For a complete new-machine setup covering OPL Base, the optional OPL App, and selected OPL Packages, use the [One Person Lab new-machine Codex bootstrap guide](https://github.com/gaofeng21cn/one-person-lab/blob/main/docs/references/current-support/opl-new-machine-codex-bootstrap.md).

You can paste this into Codex on the new machine:

```text
Please follow the official One Person Lab new-machine guide and set up this machine with the OPL agent runtime environment and the complete Codex workflow toolkit.
Source of truth: https://github.com/gaofeng21cn/one-person-lab/blob/main/docs/references/current-support/opl-new-machine-codex-bootstrap.md
```

## Developer Local-Source Tool

`scripts/install_local_plugin.py` is retained for OPL Flow repository development and local-source testing only. It is not the normal user installer, package updater, or package currentness authority.

Install a checkout payload without the profile:

```bash
python3 scripts/install_local_plugin.py --no-profile
```

Verify local-source staging:

```bash
python3 scripts/install_local_plugin.py --verify-only
scripts/verify.sh
```

This verification binds only the repository marketplace manifest, staged local plugin, exact Codex plugin readback, and versioned cache payload. It does not prove package lifecycle currentness.

## Repo Profile Sync

OPL Flow can check or write the workflow portion of an OPL-native repo profile:

```bash
python3 scripts/repo_profile.py check --repo-root /path/to/repo
python3 scripts/repo_profile.py sync --repo-root /path/to/repo
python3 scripts/repo_profile.py sync --repo-root /path/to/repo --apply
```

`sync` is a dry-run unless `--apply` is present. Apply mode preserves
repo-specific prose and only updates `contracts/opl-native-profile.json` plus
managed blocks in `AGENTS.md`. That managed block points to the
profile and do not own contracts, source, tests, runtime output, or project
truth.

## Usage

Ask Codex:

```text
Use OPL Flow for this task.
```

Codex uses the minimal profile as preferences, not as a task router. Planning, implementation, diagnosis, and verification remain model-native. Independently installed specialist skills are loaded only when their own explicit or narrow triggers apply.

`contracts/workflow-policy.json` is the machine-readable policy owner for dependencies, Full offline closure, conflicts, retired workflow surfaces, and the recommended Codex model/reasoning defaults. A `recommends` entry with `online_install_default=true` is part of the default managed dependency closure: Framework installs and updates it with OPL Flow. App Full bundles the same entries marked `offline_bundle=full`; the App does not maintain another inventory. OPL Framework executes the policy, while OPL App only requests reconciliation and displays package state and user overrides.

The runtime profile does not read `~/.codex/TASTE.md`. OPL Flow compiles its stable preference digest into `AGENTS.md`; the full TASTE file remains available for human maintenance. Repo-local `TASTE.md` files are not required.

## Compatibility With OPL App Full

OPL Flow is an official OPL Package. App Standard or Full may select it, but Base installation never requires it. The user-facing lifecycle has only three objects:

- OPL Base owns `opl`, Temporal-backed runtime dependencies, package lifecycle, and dependency/integration status.
- OPL App is the optional GUI for installing, inspecting, updating, and repairing Base and Packages; App/host carriers update the GUI itself.
- OPL Packages include MAS/MAG/RCA/OMA/BookForge/ScholarSkills and OPL Flow. Plugin/skill/profile materialization is internal package projection, not another user lifecycle.
- OPL Flow owns only the minimal `AGENTS.md` preference profile, TASTE authoring source, and package payload semantics.
- On a fresh machine with no user-level `~/.codex/AGENTS.md`, `opl packages install opl-flow` installs the plugin and rendered user profile directly.
- On a machine that already has `AGENTS.md`, the same package transaction uses Codex to preserve distinct user preferences while removing conflicting or redundant legacy workflow prose; packet review/apply is the failure fallback.
- Normal package installation registers `opl-flow@opl-agent-opl-flow-local`; `opl-flow@opl-flow-local` is reserved for the repository developer/local-source tool.
- OPL Flow changes user-owned `AGENTS.md` only after semantic merge, target-hash validation, backup, and receipt creation; OPL App only requests the Framework transaction.
- App Full packages the OPL Flow `offline_bundle=full` dependency closure; Framework applies the same package's migration and rollback policy.
- OPL Flow does not own Base/App/runtime readiness, domain truth, or package currentness; those remain on their owning Base, App, Package, and domain readbacks.

See [docs/compatibility.md](docs/compatibility.md) for the positioning matrix against Codex customization and adjacent workflow layers.

## Relationship To OPL Doc

OPL Flow is the generic preference-profile Package. OPL Doc is a separate developer support repo for OPL-family documentation governance; it is not a normal-user dependency of OPL Flow or OPL Base.

For plugin-native repos, OPL Flow owns the workflow managed block while OPL Doc
owns documentation lifecycle profile checks. The shared machine pointer is
`contracts/opl-native-profile.json`.

`opl-flow` itself is the source repository for that profile and is intentionally
self-hosted without a repo-local `contracts/opl-native-profile.json`; its root
`AGENTS.md` contains only the concise CodeGraph block.
Run `repo_profile.py check` against consumer OPL-native repos, not
as a self-check for this repository.

## Development

```bash
scripts/verify.sh
python3 /Users/gaofeng/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .
```
