# OPL Flow Compatibility And Positioning

Owner: `gaofeng`
Purpose: `opl_flow_positioning_and_compatibility`
State: `active`
Machine boundary: This page is a human-readable positioning map. Executable truth remains the plugin manifest, install script, bundled skills, and repo-native verification commands.

OPL Flow is a Codex-first, model-native preference profile. It packages a minimal `AGENTS.md`, installs a non-runtime authoring source, and leaves development methods external and on demand.

Publicly, OPL Flow should be read as a distribution of working mode, not as a
runtime, package, or domain authority. It may guide how Codex works, verifies,
and records evidence, but it cannot make OPL App, OPL Framework, OPL Packages,
or domain systems ready by itself.

## Positioning Matrix

| System | Mature practice to absorb | OPL Flow boundary |
| --- | --- | --- |
| Codex AGENTS.md / skills | Keep persistent preferences concise and scope project procedures locally. | OPL Flow owns the minimal user profile and its install/readback contract. It does not own project facts, source, tests, runtime output, or domain contracts. |
| Specialist skills | Use only for explicit requests or narrow domain/high-risk conditions that require reusable procedure. | Ordinary development remains model-native; OPL Flow neither packages nor measures a methodology bundle. |
| Ponytail | Use over-engineering review and cleanup discovery as an explicit tactical lens. | Ponytail is optional and defaults to `off`; no startup persona injection is required. |
| Trellis | Persist specs, tasks, workspace state, and closeout artifacts in versioned project surfaces. | OPL Flow absorbs the artifact discipline, but writes Durable evidence into each repo's existing docs, contracts, ledgers, or closeouts instead of creating a second `.trellis`-style truth source. |
| Claude Code skills/subagents/memory | Load specialized procedures on demand; use subagents for bounded, isolated work; keep memory/rules concise and scoped. | OPL Flow keeps `SKILL.md` entrypoints lean, requires explicit subagent write sets and stop conditions, and treats `TASTE.md` as preference rather than fact. |
| GitHub Agentic Workflows | Use scoped permissions, auditability, and safe outputs for production agent work. | `codex-ops-kit` is an explicit utility for deterministic Git lane lifecycle evidence and live GitHub release URL/asset/install-command readback; it is not part of the default profile. |

## Installed Layers

| Layer | Owner | Installed by OPL Flow |
| --- | --- | --- |
| Runtime workflow profile | OPL Flow | `~/.codex/AGENTS.md` |
| Preference authoring | OPL Flow | Non-blocking `~/.codex/TASTE.md` |
| Generic OPL Flow skill | OPL Flow | `skills/opl-flow` |
| CodeGraph bootstrap | OPL Flow profile | Initialize and Git-ignore `.codegraph/`; keep detailed tool guidance repo-local |
| Git lane and GitHub release audit | Optional OPL Flow utility | `skills/codex-ops-kit`; explicit invocation only |
| Specialist debugging / verification | Independent skills | Not vendored or measured by OPL Flow; routed only by narrow triggers |
| Simplification / over-engineering review | Ponytail | Optional companion plugin; detected but not required |
| Installation Carrier | One Person Lab App / host carrier | Not owned by OPL Flow |
| Runtime Substrate | One Person Lab / OPL App | Not owned by OPL Flow |
| Capability Packages | One Person Lab / domain repos | Not owned by OPL Flow |
| Companion Tools | One Person Lab / external tool owners | Not owned by OPL Flow |
| Codex Surface sync | One Person Lab / OPL App | Not owned by OPL Flow |
| User data and artifacts | User / domain owners | Not owned by OPL Flow |

## Install And Update Boundary

- Fresh machine: `opl packages install opl-flow` owns package installation and can install the rendered profile when user-level `~/.codex/AGENTS.md` does not exist.
- Existing Codex machine: `opl packages update opl-flow` owns package update. It must not overwrite an existing user profile and instead routes a semantic merge packet.
- Script merge policy: disabled for profile semantics. Scripts may copy, stage, back up, verify, and create packets; Codex handles semantic reconciliation.
- OPL App Full initialization can include OPL Flow alongside other payloads, but OPL Flow remains the workflow-profile lifecycle. Fresh machines use the direct profile path; existing Codex machines use the merge-packet path.
- OPL App update management must stage OPL Flow plugin payload updates separately from user profile changes. User profile changes require Codex semantic merge, review/apply, and rollback evidence.

## Verification Boundary

- `scripts/install_local_plugin.py --verify-only` is a repository developer/local-source check for the AGENTS profile, staged plugin, exact installed plugin identity, and versioned cache payload. It is not the package currentness authority.
- It does not inspect or score Superpowers, Ponytail, `codex-ops-kit`, independent specialist skills, OPL App runtime, domain packages, or project readiness.
- OPL App does not package or auto-install Superpowers.
- Runtime substrate, capability packages, companion tools, Codex surface sync, release, latest/currentness, OPL App Full, MAS/MAG/RCA/BookForge, and owner-route status remain on their owning surfaces.

## Canonical External References

- Codex customization: https://developers.openai.com/codex/concepts/customization
- Ponytail: https://github.com/DietrichGebert/ponytail
- Trellis: https://github.com/mindfold-ai/Trellis
- Claude Code skills: https://docs.anthropic.com/en/docs/claude-code/skills
- Claude Code subagents: https://docs.anthropic.com/en/docs/claude-code/sub-agents
- Claude Code memory: https://docs.anthropic.com/en/docs/claude-code/memory
- GitHub Agentic Workflows: https://github.github.com/gh-aw/
