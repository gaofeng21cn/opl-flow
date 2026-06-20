# OPL Flow Compatibility And Positioning

Owner: `gaofeng`
Purpose: `opl_flow_positioning_and_compatibility`
State: `active`
Machine boundary: This page is a human-readable positioning map. Executable truth remains the plugin manifest, install scripts, bundled skills, companion checker output, and repo-native verification commands.

OPL Flow is a Codex-first workflow profile and guardrail layer. It is not a second implementation of Superpowers, Trellis, Claude Code, or GitHub Agentic Workflows. It packages the workstation workflow into a Codex plugin, installs profile prompts, bundles OPL Flow-owned guardrails, and routes to external execution skills when those skills are the right owner.

## Positioning Matrix

| System | Mature practice to absorb | OPL Flow boundary |
| --- | --- | --- |
| Codex AGENTS.md / skills | Keep persistent agent behavior in scoped instruction files; keep reusable procedures in skills; use plugins for distribution. | OPL Flow owns the Codex workflow profile, `opl-flow` skill, and bundled guardrails. It does not own project facts, source, tests, runtime output, or domain contracts. |
| Superpowers | Use explicit skills for systematic debugging, verification before completion, TDD, worktree isolation, and v6 planning / SDD / review flows when the task warrants them. | Superpowers remains the execution surface for its official skills. OPL Flow routes to the active local Superpowers profile and keeps the default profile lighter than full always-on Superpowers. `lite` is the quiet default, `expanded` exposes v6 long-chain implementation helpers, and `full` is an explicit user choice. |
| Trellis | Persist specs, tasks, workspace state, and closeout artifacts in versioned project surfaces. | OPL Flow absorbs the artifact discipline, but writes Durable evidence into each repo's existing docs, contracts, ledgers, or closeouts instead of creating a second `.trellis`-style truth source. |
| Claude Code skills/subagents/memory | Load specialized procedures on demand; use subagents for bounded, isolated work; keep memory/rules concise and scoped. | OPL Flow keeps `SKILL.md` entrypoints lean, requires explicit subagent write sets and stop conditions, and treats `TASTE.md` as preference rather than fact. |
| GitHub Agentic Workflows | Use guardrails, scoped permissions, auditability, cost/ops visibility, and safe outputs for production agent work. | `codex-ops-kit` owns high-risk Codex ops gates for lane lifecycle, currentness claims, generated/runtime config drift, secret freshness, and long evidence chains. |

## Installed Layers

| Layer | Owner | Installed by OPL Flow |
| --- | --- | --- |
| Workflow profile | OPL Flow | `~/.codex/AGENTS.md`, `~/.codex/TASTE.md`, planner/executor/debugger/verifier prompts |
| Generic OPL Flow skill | OPL Flow | `skills/opl-flow` |
| Risk selection guardrail | OPL Flow | `skills/risk-based-development-flow` |
| High-risk ops guardrail | OPL Flow | `skills/codex-ops-kit` |
| Debugging / verification execution | Superpowers / companion skills | Not vendored by OPL Flow; routed to when installed |
| OPL runtime and App readiness | One Person Lab / OPL App | Not owned by OPL Flow |
| MAS/MAG/RCA/OMA/BookForge domain agents | Domain repos and plugins | Not owned by OPL Flow |

## Readiness Claims

- `scripts/check_companion_skills.py` default mode checks core profile compatibility and reports optional companion coverage.
- `scripts/check_companion_skills.py --strict` fails closed unless the OPL Flow-owned guardrails are discoverable.
- `match_details` and `sources` identify whether a skill came from the source checkout, installed plugin, user skill root, skills manager, plugin cache, or custom root.
- `superpowers_profile.profile` reports the active local Superpowers profile as `lite`, `expanded`, `full`, `custom`, or `not_configured`; this is a workflow readback, not an OPL App/runtime readiness claim.
- Runtime, release, latest/currentness, OPL App Full, MAS/MAG/RCA/BookForge, and owner-route readiness require their own live artifacts or owner receipts. OPL Flow tests cannot prove those surfaces ready.

## Canonical External References

- Codex customization: https://developers.openai.com/codex/concepts/customization
- Superpowers: https://github.com/obra/Superpowers
- Trellis: https://github.com/mindfold-ai/Trellis
- Claude Code skills: https://docs.anthropic.com/en/docs/claude-code/skills
- Claude Code subagents: https://docs.anthropic.com/en/docs/claude-code/sub-agents
- Claude Code memory: https://docs.anthropic.com/en/docs/claude-code/memory
- GitHub Agentic Workflows: https://github.github.com/gh-aw/
