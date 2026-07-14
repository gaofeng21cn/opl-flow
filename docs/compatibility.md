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
| Ponytail | Retired conflict for the optimized OPL Flow profile. | Package migration backs up the plugin, config, and hooks, then removes them from active discovery unless explicitly kept. The backup remains available for rollback. |
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
| Git lane and GitHub release audit | Optional OPL Flow utility | `optional-skills/codex-ops-kit`; not exposed by the default plugin and installed only by explicit selection |
| Specialist debugging / verification | Independent skills | Not vendored or measured by OPL Flow; routed only by narrow triggers |
| Simplification / over-engineering review | Model-native | No global persona or hook dependency |
| OPL Base | One Person Lab | Not installed or updated by OPL Flow |
| OPL App | One Person Lab App / host carrier | Optional GUI; not installed or updated by OPL Flow |
| OPL Packages | One Person Lab + package owner | OPL Flow participates as one Package; it does not own other Packages |
| Base dependencies/integrations | One Person Lab / external tool owners | Not independent user modules and not owned by OPL Flow |
| User data and artifacts | User / domain owners | Not owned by OPL Flow |

## Install And Update Boundary

- Fresh machine: `opl packages install opl-flow` owns package installation and can install the rendered profile when user-level `~/.codex/AGENTS.md` does not exist.
- Existing Codex machine: `opl packages update opl-flow` owns package update and runs the same optimize transaction after source refresh.
- Script merge policy: scripts remove only policy-declared marker blocks. Codex handles unmarked semantic reconciliation; target-hash validation, backup, receipt, and rollback protect the applied result.
- OPL App Full initialization can include OPL Flow alongside other payloads, but OPL Flow remains the workflow-profile lifecycle. Fresh machines use the direct profile path; existing Codex machines use the merge-packet path.
- After any successful OPL App carrier version change, the App requests generic Framework reconciliation for OPL Base and all installed Packages. If OPL Flow is installed, Framework performs its ordinary dependency, conflict, profile, receipt, and rollback transaction. The App does not duplicate Flow policy, maintain a second dependency list, or mutate `AGENTS.md` directly.

## Verification Boundary

- `scripts/install_local_plugin.py --verify-only` is a repository developer/local-source check for the AGENTS profile, staged plugin, exact installed plugin identity, and versioned cache payload. It is not the package currentness authority.
- It does not score project readiness or domain quality. OPL Framework reads its conflict/retirement policy during an explicit OPL Flow package install, update, optimize, or generic post-App-update reconciliation of installed Packages.
- Framework migration backs up and retires the historical surfaces declared by the workflow policy.
- Base runtime/dependencies, App release/currentness, other Packages, MAS/MAG/RCA/BookForge domain truth, and owner-route status remain on their owning surfaces.

## Canonical External References

- Codex customization: https://developers.openai.com/codex/concepts/customization
- Workflow dependency and migration policy: `contracts/workflow-policy.json`
- Trellis: https://github.com/mindfold-ai/Trellis
- Claude Code skills: https://docs.anthropic.com/en/docs/claude-code/skills
- Claude Code subagents: https://docs.anthropic.com/en/docs/claude-code/sub-agents
- Claude Code memory: https://docs.anthropic.com/en/docs/claude-code/memory
- GitHub Agentic Workflows: https://github.github.com/gh-aw/
