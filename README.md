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

The composer only performs deterministic module rendering. It does not do
semantic merging. If a target machine already has a user-level `AGENTS.md`,
semantic reconciliation must be done by Codex after reading the existing file
and the OPL Flow profile intent, not by heuristic script rules.

## Install Or Update

```bash
opl packages install opl-flow
opl packages update opl-flow
```

The OPL Framework package lifecycle owns installation, update, rollback, and package currentness. It installs:

- the managed OPL Flow plugin payload and Codex discovery entry
- Runtime workflow profile: `~/.codex/AGENTS.md`
- Non-runtime authoring source: `~/.codex/TASTE.md`

On a machine without `~/.codex/AGENTS.md`, the package lifecycle writes the rendered OPL
Flow profile directly. On a machine that already has user-level `AGENTS.md`, the
package lifecycle does not overwrite it. It installs the plugin payload, then creates a
merge packet under `~/.codex/state/opl-flow/profile-merge/<timestamp>/` with
the existing profile, candidate OPL Flow profile, module manifest, module
sources, and a Codex merge prompt. Semantic merging must be performed by Codex
from that packet; the package lifecycle does not use heuristic script merging for
profile semantics.

When a semantic merge is required, follow the merge packet and apply route returned by the package command. The package lifecycle remains the user-facing owner of the operation and its readback.

`~/.codex/TASTE.md` is the human-maintained preference authoring source, not a session input. Its stable digest is compiled into `AGENTS.md`; its absence or drift does not fail runtime readiness. Repo-specific facts, local boundaries, and project development rules belong in `AGENTS.md`, docs, contracts, source, tests, and runtime/readback evidence.

OPL App does not package or auto-install Superpowers. Independently installed specialist skills remain available through their own narrow frontmatter triggers.

Use the package command's readback for installed version and package currentness. OPL Flow does not maintain a second companion or readiness checker.

Restart Codex after installation.

## Optional Intelligence Enhancement

OPL Flow may declare a preference for optional CodexCont-style continuation support. OPL Base/System and Managed Update own dependency installation, Codex configuration, launchd/systemd/container service lifecycle, status, repair, rollback, and removal. This repository does not install or operate that service.

For a complete new-machine setup that installs the OPL runtime, One Person Lab App, MAS/MAG/RCA/OMA agent surfaces, OPL Flow, OPL Doc, and companion tools, use the [One Person Lab new-machine Codex bootstrap guide](https://github.com/gaofeng21cn/one-person-lab/blob/main/docs/references/current-support/opl-new-machine-codex-bootstrap.md). BookForge is tracked as a new OPL-standard repo, but default Connect/App visibility needs separate admission evidence.

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

The runtime profile does not read `~/.codex/TASTE.md`. OPL Flow compiles its stable preference digest into `AGENTS.md`; the full TASTE file remains available for human maintenance. Repo-local `TASTE.md` files are not required.

## Compatibility With OPL App Full

OPL Flow is a required workflow plugin package in One Person Lab App Standard and Full. It participates in the managed OPL Package lifecycle for plugin delivery and readback, while owning only Workflow Profile semantics and never becoming part of Runtime Substrate. Treat the layers separately:

- Installation Carrier updates are owned by One Person Lab App and the host/container carrier: macOS standard updater/Homebrew, Docker/WebUI image host route, or Linux package carrier.
- Runtime Substrate updates cover App-owned runtime payloads such as the embedded Codex executor, Temporal archive, Node/Python/uv, native helpers, and OPL Framework runtime.
- Capability Packages cover MAS/MAG/RCA/OMA/BookForge/ScholarSkills managed modules and the separately typed OPL Flow workflow plugin package.
- Companion Tools and support skills cover OfficeCLI, MinerU, UI/UX, and similar helpers; official OpenAI Primary Runtime PDF/Office capabilities are not mirrored as OPL skills.
- Codex Surface sync covers plugin registry, plugin-packaged skills, generated OPL plugin surfaces, and reload guidance.
- OPL Flow owns only the minimal `AGENTS.md` preference profile, TASTE authoring source, plugin, and installation/readback contract.
- On a fresh machine with no user-level `~/.codex/AGENTS.md`, App-managed initialization can install the OPL Flow plugin and rendered user profile directly.
- On a machine that already has Codex and user-level `AGENTS.md`, App-managed initialization must use OPL Flow's non-overwrite install path: install or stage the plugin payload, generate the merge packet, and let Codex perform the semantic merge before any profile apply.
- OPL Flow installs the user-level preference profile and `opl-flow@opl-flow-local`; its optional utilities are not profile dependencies or readiness signals.
- OPL Flow should not overwrite user-owned `AGENTS.md`, and OPL App session context should respect existing user profile files.
- OPL App does not package or auto-install Superpowers; independently installed specialist skills remain user-owned.
- OPL Flow does not own OPL App/runtime readiness. Runtime substrate, companion tools, domain module health, GUI shell, App first-run state, and Full readiness belong to One Person Lab App / OPL Framework surfaces and should be checked there, not treated as OPL Flow profile gaps.
- OPL App update management for OPL Flow must split plugin payload updates from profile updates. Plugin payloads can be staged and verified; user-level profile changes require a Codex semantic merge packet, review/apply, and rollback evidence.

See [docs/compatibility.md](docs/compatibility.md) for the positioning matrix against Codex customization and adjacent workflow layers.

## Relationship To OPL Doc

OPL Flow is the generic workflow layer. OPL Doc is the domain skill that governs OPL-family developer documentation lifecycle. OPL Doc can use OPL Flow's Durable writeback, subagent contract, and verifier gates, but the two should stay separate.

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
