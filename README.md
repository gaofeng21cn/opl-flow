# OPL Flow

OPL Flow is a lightweight Codex workflow profile for pragmatic local engineering. It packages decision lenses, durable guardrails, and installation/readback checks into a reusable Codex plugin and user profile.

## Public Role Boundary

OPL Flow is the distribution of a working mode: workflow profile, decision lenses,
guardrail skills, and install/update guidance for Codex. It owns the
`workflow_profile` layer only.

OPL Flow is not runtime truth, package truth, or domain truth. It does not own
OPL App readiness, OPL Framework runtime behavior, OPL Packages lifecycle,
release currentness, companion-tool health, project facts, source behavior, or
domain acceptance. Those claims stay with the owning App, Framework, package,
repo, runtime, contract, test, or owner-receipt surface.

It is inspired by Trellis and Superpowers, but stays Codex-first:

- Direct / Inline / Durable task tiers.
- Planner / Executor / Debugger / Verifier decision lenses used continuously by one agent.
- Risk-aware evidence and narrow TDD rules in TASTE/AGENTS and the verifier lens.
- Bundled `codex-ops-kit` for fail-closed Git worktree/subagent lane evidence and live GitHub release URL/asset/install-command audits.
- Codex inline execution by default.
- Subagent/worktree lane contract for scoped parallel work.
- Durable evidence and lesson writeback.
- Verification before completion, including Chinese "完成度审计" for target-state delivery.
- Root-Cause Depth Gate for stalls, repeated failures, heartbeat findings, runtime/currentness/readiness drift, and multi-thread supervision.
- Fresh evidence boundaries for runtime truth, readiness, currentness, release, CI, and owner-route claims.
- CodeGraph marker block preservation for projects that rely on CodeGraph injection.
- RTK shell preference for compact command output when available.
- Repo-local workflow profile check/sync for OPL-native development directories.

## User Profile Source

`templates/AGENTS.md` is a rendered profile, not the only source. The source is
split into ordered modules under `profile/modules/` and declared by
`profile/manifest.json`:

- user preferences
- role and baseline
- workflow core
- guardrails
- ops and authority core
- capability adapters
- tool preferences
- managed block policy

Regenerate and check the rendered profile with:

```bash
python3 scripts/profile_compose.py write
python3 scripts/profile_compose.py check
```

The composer only performs deterministic module rendering. It does not do
semantic merging. If a target machine already has a user-level `AGENTS.md`,
semantic reconciliation must be done by Codex after reading the existing file
and the OPL Flow profile intent, not by heuristic script rules.

## Install On A New Machine

```bash
git clone https://github.com/gaofeng21cn/opl-flow.git
cd opl-flow
python3 scripts/install_local_plugin.py
```

This stages and installs:

- local plugin and independent marketplace root: `~/plugins/opl-flow`
- exact Codex plugin: `opl-flow@opl-flow-local`, verified installed and enabled
- Codex workflow profile:
  - `~/.codex/AGENTS.md`
  - `~/.codex/TASTE.md`
  - `~/.codex/prompts/planner.md`
  - `~/.codex/prompts/executor.md`
  - `~/.codex/prompts/debugger.md`
  - `~/.codex/prompts/verifier.md`

On a machine without `~/.codex/AGENTS.md`, the installer writes the rendered OPL
Flow profile directly. On a machine that already has user-level `AGENTS.md`, the
installer does not overwrite it. It installs the plugin payload, then creates a
merge packet under `~/.codex/state/opl-flow/profile-merge/<timestamp>/` with
the existing profile, candidate OPL Flow profile, module manifest, module
sources, and a Codex merge prompt. Semantic merging must be performed by Codex
from that packet; the installer does not use heuristic script merging for
profile semantics.

The pending install returns a nonzero status. After reviewing the complete
`output/` set and `merge-report.md`, apply it and record the approved receipt:

```bash
python3 scripts/install_local_plugin.py --apply-merge-packet <packet-path>
python3 scripts/install_local_plugin.py --verify-only
```

Packet apply is bound to the candidate source and existing target fingerprints
captured at packet creation. If either side changes, generate a new packet.

`~/.codex/TASTE.md` carries default AI work principles. Repo-specific facts, local boundaries, and project development rules belong in `AGENTS.md`, docs, contracts, source, tests, and runtime/readback evidence rather than duplicated repo-local taste files.

The profile routes to companion skills by name. OPL Flow bundles only `codex-ops-kit`, because Git lane and public release checks need deterministic fail-closed machinery; general risk judgment stays in the thin profile. OPL Flow is a required Standard and Full `workflow_plugin_package`, while its semantic ownership remains limited to the Workflow Profile layer. OPL App Full may install the Superpowers execution surface, common companion skills, companion tools, and other OPL capability packages through their own lifecycle planes; OPL Flow only detects and routes to those surfaces when present. It preserves the current local Superpowers profile by default; switching to official full Superpowers is an explicit user choice, not an installer side effect. `agent-browser`, Ponytail, RTK, and CodeGraph remain optional machine-level enhancements.

Check a machine with:

```bash
python3 scripts/check_companion_skills.py
```

The checker reports both the Superpowers bundle readiness and the active local Superpowers profile (`lite`, `expanded`, `full`, `custom`, or `not_configured`). `lite` and `expanded` keep the local routing profile and leave upstream `using-superpowers` disabled; `full` links the complete upstream skills directory and enables the official bootstrap.

Ponytail is treated as an optional simplification lens for YAGNI / stdlib-first / over-engineering review. OPL Flow keeps the workstation default at `lite`:

```bash
mkdir -p ~/.config/ponytail
printf '{\n  "defaultMode": "lite"\n}\n' > ~/.config/ponytail/config.json
codex plugin marketplace add DietrichGebert/ponytail
codex plugin add ponytail@ponytail
```

The Ponytail plugin owns its active mode. OPL Flow does not claim task-driven automatic `full/ultra` switches; it routes `ponytail-audit` for broad candidate discovery and `ponytail-review` for concrete diffs. Ponytail must not override risk-aware evidence, `codex-ops-kit` Git/release evidence, verifier, fresh-evidence, or completion-audit rules.

OPL Flow routes Ponytail by artifact shape: `ponytail-audit` is for whole-repo or cross-repo cleanup candidate discovery; `ponytail-review` is for a concrete diff, PR, commit range, or worktree lane before absorption when the change is a non-trivial cleanup/refactor/wrapper-retirement/dependency-thinning lane.

Use strict mode when checking that the profile, exact installed plugin, and runtime-discoverable guardrails are ready:

```bash
python3 scripts/check_companion_skills.py --strict
```

Restart Codex after installation.

## Enable Intelligence Enhancement

OPL Flow owns the CodexCont "智力增强模式" installer/configuration entry:

```bash
python3 scripts/intelligence_enhancement.py enable --bootstrap-opl
python3 scripts/intelligence_enhancement.py status
```

The script uses CodexCont's GitHub source directly:

```bash
uvx --from git+https://github.com/ZhenHuangLab/CodexCont codexcont ...
```

One Person Lab / OPL App only delegates to this OPL Flow script for the UI and
`opl app action` switch. The CodexCont source, local proxy config, Codex config
mutation, and service registration are OPL Flow-owned behavior.

Use `repair` when the local CodexCont service is configured but not healthy:

```bash
python3 scripts/intelligence_enhancement.py repair
```

Uninstall stays explicit:

```bash
python3 scripts/intelligence_enhancement.py uninstall --confirmation uninstall_codexcont
```

For a complete new-machine setup that installs the OPL runtime, One Person Lab App, MAS/MAG/RCA/OMA agent surfaces, OPL Flow, OPL Doc, and companion tools, use the [One Person Lab new-machine Codex bootstrap guide](https://github.com/gaofeng21cn/one-person-lab/blob/main/docs/references/current-support/opl-new-machine-codex-bootstrap.md). BookForge is tracked as a new OPL-standard repo, but default Connect/App visibility needs separate admission evidence.

You can paste this into Codex on the new machine:

```text
Please follow the official One Person Lab new-machine guide and set up this machine with the OPL agent runtime environment and the complete Codex workflow toolkit.
Source of truth: https://github.com/gaofeng21cn/one-person-lab/blob/main/docs/references/current-support/opl-new-machine-codex-bootstrap.md
```

For the shorter CodexCont path, paste:

```text
安装并配置 gaofeng21cn/opl-flow 并开启智力增强模式。

执行口径：
1. 读取 https://github.com/gaofeng21cn/opl-flow 的 README。
2. 安装或刷新 OPL Flow。
3. 在 opl-flow checkout 中运行：
   python3 scripts/intelligence_enhancement.py enable --bootstrap-opl
   python3 scripts/intelligence_enhancement.py status

要求：如果 OPL CLI 缺失，允许通过官方 One Person Lab App installer 安装；最终报告智力增强模式状态、CodexCont 服务状态、Codex provider base URL，以及关闭/卸载命令。
```

## Install Plugin Only

```bash
python3 scripts/install_local_plugin.py --no-profile
```

## Verify

```bash
python3 scripts/install_local_plugin.py --verify-only
scripts/verify.sh
```

Verification binds the repository marketplace manifest, staged plugin, exact Codex plugin readback, and the versioned Codex cache payload. Reinstalling the same version still refreshes that cache.

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

The profile routes work by shape:

- Direct: answer directly with minimal reads.
- Inline: main session implements and verifies.
- Durable: persist plan, evidence, decision, or runbook in the right file.

It also routes evidence-sensitive work:

- Risk-based verification: classify the risk, choose a verification budget, and avoid TDD/test bloat unless it proves a concrete regression.
- High-risk Git/release evidence: use `codex-ops-kit` before Git lane start/absorb/closeout or before claiming a public GitHub release URL, asset, or exact install command is current.
- Root-cause supervision: stalls, repeated failures, heartbeat findings, runtime/currentness/readiness drift, and multi-thread stops must identify the visible symptom, direct failing boundary, cross-surface evidence, owner surface, and repair or decision path before closeout.
- Completion audits: for "全部落地 / 一步到位 / 彻底解决" style goals, verify against the original target plan and report Chinese "完成度审计" with status, percent, fresh evidence, gaps, and next actions.
- Complexity regression: for non-trivial cleanup/refactor/worktree lanes, review the concrete diff with `ponytail-review` before absorption; use `ponytail-audit` only for candidate discovery.

The profile reads AI work principles from the user-level `~/.codex/TASTE.md`. Repo-local `TASTE.md` files are no longer required for OPL-native repositories; local facts, stricter rules, and project-specific development policy should live in `AGENTS.md`, docs, contracts, source, tests, or runtime/readback surfaces. Taste never overrides code, contracts, docs, runtime output, or direct user instructions.

## Compatibility With OPL App Full

OPL Flow is a required workflow plugin package in One Person Lab App Standard and Full. It participates in the managed OPL Package lifecycle for plugin delivery and readback, while owning only Workflow Profile semantics and never becoming part of Runtime Substrate. Treat the layers separately:

- Installation Carrier updates are owned by One Person Lab App and the host/container carrier: macOS standard updater/Homebrew, Docker/WebUI image host route, or Linux package carrier.
- Runtime Substrate updates cover App-owned runtime payloads such as the embedded Codex executor, Temporal archive, Node/Python/uv, native helpers, and OPL Framework runtime.
- Capability Packages cover MAS/MAG/RCA/OMA/BookForge/ScholarSkills managed modules and the separately typed OPL Flow workflow plugin package.
- Companion Tools and support skills cover the complete upstream OfficeCLI skill family, MinerU, UI/UX, Superpowers, and similar helpers; official OpenAI Primary Runtime PDF/Office capabilities are not mirrored as OPL skills.
- Codex Surface sync covers plugin registry, plugin-packaged skills, generated OPL plugin surfaces, and reload guidance.
- OPL Flow owns only the Workflow Profile semantics: `AGENTS.md`, `TASTE.md`, decision lenses, the `opl-flow` plugin, and OPL Flow-owned guardrails.
- On a fresh machine with no user-level `~/.codex/AGENTS.md`, App-managed initialization can install the OPL Flow plugin and rendered user profile directly.
- On a machine that already has Codex and user-level `AGENTS.md`, App-managed initialization must use OPL Flow's non-overwrite install path: install or stage the plugin payload, generate the merge packet, and let Codex perform the semantic merge before any profile apply.
- OPL Flow installs the user-level workflow profile, `opl-flow@opl-flow-local`, and the OPL Flow-owned mechanical guardrail `codex-ops-kit`.
- OPL Flow should not overwrite user-owned `AGENTS.md`, and OPL App session context should respect existing user profile files.
- Superpowers should remain the execution surface for its official skills; OPL Flow only routes to the active local profile. `lite` keeps the focused debugger/TDD/verifier subset, `expanded` adds broad planning/worktree helpers, and `full` is reserved for explicit official Superpowers use.
- Ponytail can be installed alongside OPL Flow as an optional simplification lens with default `lite`; use audit/review routing for YAGNI and over-engineering checks, not as a replacement for evidence, ops, or verification gates.
- OPL Flow does not own OPL App/runtime readiness. Runtime substrate, companion tools, domain module health, GUI shell, App first-run state, and Full readiness belong to One Person Lab App / OPL Framework surfaces and should be checked there, not treated as OPL Flow profile gaps.
- OPL App update management for OPL Flow must split plugin payload updates from profile updates. Plugin payloads can be staged and verified; user-level profile changes require a Codex semantic merge packet, review/apply, and rollback evidence.

See [docs/compatibility.md](docs/compatibility.md) for the positioning matrix against Codex customization, Superpowers, Trellis, Claude Code skills/subagents/memory, and GitHub Agentic Workflows.

## Relationship To OPL Doc

OPL Flow is the generic workflow layer. OPL Doc is the domain skill that governs OPL-family developer documentation lifecycle. OPL Doc can use OPL Flow's Durable writeback, subagent contract, and verifier gates, but the two should stay separate.

For plugin-native repos, OPL Flow owns the workflow managed block while OPL Doc
owns documentation lifecycle profile checks. The shared machine pointer is
`contracts/opl-native-profile.json`.

`opl-flow` itself is the source repository for that profile and is intentionally
self-hosted without a repo-local `contracts/opl-native-profile.json` or `AGENTS.md`.
Run `repo_profile.py check` against consumer OPL-native repos, not
as a self-check for this repository.

## Development

```bash
scripts/verify.sh
python3 /Users/gaofeng/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .
```
