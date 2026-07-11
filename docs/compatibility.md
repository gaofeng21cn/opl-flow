# OPL Flow Compatibility And Positioning

Owner: `gaofeng`
Purpose: `opl_flow_positioning_and_compatibility`
State: `active`
Machine boundary: This page is a human-readable positioning map. Executable truth remains the plugin manifest, install scripts, bundled skills, companion checker output, and repo-native verification commands.

OPL Flow is a Codex-first workflow profile and guardrail layer. In the OPL install taxonomy it owns the `workflow_profile` layer only. It is not a second implementation of Superpowers, Trellis, Claude Code, GitHub Agentic Workflows, the OPL runtime substrate, OPL Packages, companion tools, or Codex plugin surface sync. It packages one `AGENTS.md` runtime profile into a Codex plugin, installs non-blocking authoring/compatibility surfaces, bundles OPL Flow-owned guardrails, and routes to external specialist skills when those skills are the right owner.

Publicly, OPL Flow should be read as a distribution of working mode, not as a
runtime, package, or domain authority. It may guide how Codex works, verifies,
and records evidence, but it cannot make OPL App, OPL Framework, OPL Packages,
or domain systems ready by itself.

## Positioning Matrix

| System | Mature practice to absorb | OPL Flow boundary |
| --- | --- | --- |
| Codex AGENTS.md / skills | Keep persistent agent behavior in scoped instruction files; keep reusable procedures in skills; use plugins for distribution. | OPL Flow owns `AGENTS.md` as the only runtime profile, plus its install/readback contract and bundled guardrails. It does not own project facts, source, tests, runtime output, or domain contracts. |
| Superpowers | Use explicit skills for repeated/complex debugging, terminal verification, selected TDD, worktree isolation, and v6 planning/review flows when the task warrants them. | Superpowers remains the execution surface for specialist procedures. Its local verifier/debugger/TDD entrypoints are narrow; broad planning/worktree helpers stay outside the default path. |
| Ponytail | Use YAGNI, stdlib/native-first implementation, over-engineering review, and cleanup candidate discovery as a tactical simplification lens. | Ponytail is optional. `lite` injects a short delta once at root startup; `ponytail-audit` and `ponytail-review` are explicit. It must not override OPL Flow scope, evidence, authority, or completion rules. |
| Trellis | Persist specs, tasks, workspace state, and closeout artifacts in versioned project surfaces. | OPL Flow absorbs the artifact discipline, but writes Durable evidence into each repo's existing docs, contracts, ledgers, or closeouts instead of creating a second `.trellis`-style truth source. |
| Claude Code skills/subagents/memory | Load specialized procedures on demand; use subagents for bounded, isolated work; keep memory/rules concise and scoped. | OPL Flow keeps `SKILL.md` entrypoints lean, requires explicit subagent write sets and stop conditions, and treats `TASTE.md` as preference rather than fact. |
| GitHub Agentic Workflows | Use guardrails, scoped permissions, auditability, cost/ops visibility, and safe outputs for production agent work. | `codex-ops-kit` keeps only deterministic Git lane lifecycle evidence and live GitHub release URL/asset/install-command readback; the profile and owning repos handle general policy and domain currentness. |

## Installed Layers

| Layer | Owner | Installed by OPL Flow |
| --- | --- | --- |
| Runtime workflow profile | OPL Flow | `~/.codex/AGENTS.md` |
| Preference authoring and prompt compatibility | OPL Flow | Non-blocking `~/.codex/TASTE.md` and explicit planner/executor/debugger/verifier prompts |
| Generic OPL Flow skill | OPL Flow | `skills/opl-flow` |
| Risk-aware evidence selection | OPL Flow profile | `AGENTS.md`; no separate prose-router skill or mandatory verifier prompt |
| Git lane and GitHub release audit | OPL Flow | `skills/codex-ops-kit` |
| Debugging / verification execution | Superpowers / companion skills | Not vendored by OPL Flow; routed to when installed |
| Simplification / over-engineering review | Ponytail | Optional companion plugin; detected but not required |
| Installation Carrier | One Person Lab App / host carrier | Not owned by OPL Flow |
| Runtime Substrate | One Person Lab / OPL App | Not owned by OPL Flow |
| Capability Packages | One Person Lab / domain repos | Not owned by OPL Flow |
| Companion Tools | One Person Lab / external tool owners | Not owned by OPL Flow |
| Codex Surface sync | One Person Lab / OPL App | Not owned by OPL Flow |
| User data and artifacts | User / domain owners | Not owned by OPL Flow |

## Install And Update Boundary

- Fresh machine: if user-level `~/.codex/AGENTS.md` does not exist, OPL Flow can install the rendered profile directly.
- Existing Codex machine: if user-level `~/.codex/AGENTS.md` exists, OPL Flow must not overwrite it. The installer creates a profile merge packet and requires Codex semantic merge.
- Script merge policy: disabled for profile semantics. Scripts may copy, stage, back up, verify, and create packets; Codex handles semantic reconciliation.
- OPL App Full initialization can include OPL Flow alongside other payloads, but OPL Flow remains the workflow-profile lifecycle. Fresh machines use the direct profile path; existing Codex machines use the merge-packet path.
- OPL App update management must stage OPL Flow plugin payload updates separately from user profile changes. User profile changes require Codex semantic merge, review/apply, and rollback evidence.

## Readiness Claims

- `scripts/check_companion_skills.py` default mode reports profile, plugin, runtime guardrail, and optional companion state without packaging source candidates as readiness.
- `scripts/check_companion_skills.py --strict` fails closed unless the AGENTS runtime profile, exact installed plugin/cache payload, and source-matching runtime guardrails are ready. TASTE/prompt drift remains diagnostic only.
- `match_details` distinguishes source/staged candidates from runtime-discoverable roots and deduplicates resolved paths.
- `superpowers_profile.profile` reports the active local Superpowers profile as `lite`, `expanded`, `full`, `custom`, or `not_configured`; this is a workflow readback, not an OPL App/runtime readiness claim.
- `ponytail.config.default_mode` reports the configured startup mode; `ponytail.hooks` reads the installed cache and confirms root startup only, no subagent hook, and a 5-10 line `lite` delta. The reproducible overlay is `compat/ponytail-gpt56.patch` against upstream `14a0d795`.
- Ponytail readiness only proves the simplification lens is available. It does not prove any cleanup is safe; deletion, absorption, runtime/currentness, and owner-route claims still need repo-native evidence.
- Runtime substrate, capability packages, companion tools, Codex surface sync, release, latest/currentness, OPL App Full, MAS/MAG/RCA/BookForge, and owner-route readiness require their own live artifacts or owner receipts. OPL Flow tests cannot prove those surfaces ready.

## Canonical External References

- Codex customization: https://developers.openai.com/codex/concepts/customization
- Superpowers: https://github.com/obra/Superpowers
- Ponytail: https://github.com/DietrichGebert/ponytail
- Trellis: https://github.com/mindfold-ai/Trellis
- Claude Code skills: https://docs.anthropic.com/en/docs/claude-code/skills
- Claude Code subagents: https://docs.anthropic.com/en/docs/claude-code/sub-agents
- Claude Code memory: https://docs.anthropic.com/en/docs/claude-code/memory
- GitHub Agentic Workflows: https://github.github.com/gh-aw/
