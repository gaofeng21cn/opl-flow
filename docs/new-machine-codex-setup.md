# OPL Flow New Machine Setup

Owner: `gaofeng`
Purpose: `new_machine_opl_flow_profile_setup`
State: `active`
Machine boundary: Human-readable bootstrap runbook. The executable truth remains each repository installer, App release asset, OPL CLI output, Codex plugin registry, and repo-native verification command.

This page installs the OPL Flow Codex workflow profile only.

For the complete OPL family setup that installs the OPL runtime, One Person Lab App, MAS/MAG/RCA/OMA agent surfaces, OPL Flow, OPL Doc, and companion tools, use the canonical One Person Lab guide:

https://github.com/gaofeng21cn/one-person-lab/blob/main/docs/references/current-support/opl-new-machine-codex-bootstrap.md

## Copy This Into Codex

```text
请按 OPL Flow 帮我安装或刷新这台机器的 Codex 工作流 profile。

Source of truth:
- OPL Flow: https://github.com/gaofeng21cn/opl-flow/blob/main/docs/new-machine-codex-setup.md

目标:
1. 安装并验证 OPL Flow，让 Codex 获得用户级 AGENTS.md、TASTE.md、planner/executor/debugger/verifier 角色库和 opl-flow 插件。
2. 完成后报告安装路径、备份位置、验证命令输出摘要、仍需人工处理的权限或网络问题。

约束:
- 修改前读取当前机器已有 ~/.codex、~/.agents/plugins/marketplace.json、~/plugins 和 opl-flow checkout 状态。
- 不覆盖用户已有配置；若安装器会替换用户级 profile，确认其备份路径。
- 遇到鉴权、网络、macOS 权限、GitHub 登录或系统安装权限阻塞时，停止并给出精确恢复步骤。
```

## Install Order

### 1. OPL Flow

OPL Flow owns the Codex-side working profile: user-level `AGENTS.md`, `TASTE.md`, role prompts, risk-based evidence routing, high-risk Codex ops routing, subagent/worktree lane contracts, Durable writeback, and completion verification.

```bash
git clone https://github.com/gaofeng21cn/opl-flow.git
cd opl-flow
python3 scripts/install_local_plugin.py
python3 scripts/install_local_plugin.py --verify-only
python3 scripts/verify.py
```

If the machine already uses SSH keys for GitHub, the clone URL can be `git@github.com:gaofeng21cn/opl-flow.git`.

Restart Codex after installation so plugin and skill discovery refresh.

If this machine was installed through One Person Lab App Full, the Superpowers execution surface and common companion skills are normally already packaged. OPL Flow is compatible with that setup and should not duplicate or replace those skills.

For the full OPL Flow guardrail envelope, confirm the remaining OPL Flow-native guardrails are installed and discoverable:

- `risk-based-development-flow`
- `codex-ops-kit`

OPL App Full / Superpowers normally covers:

- `systematic-debugging`
- `verification-before-completion`
- `using-git-worktrees`
- `test-driven-development`
- `mineru-document-extractor`

Optional machine-level enhancements:

- `agent-browser`
- RTK
- CodeGraph MCP/index

OPL Flow installs routing and profile files; it does not vendor those skills or machine tools.

Check the current machine with:

```bash
python3 scripts/check_companion_skills.py
```

The default checker separates core profile compatibility from full guardrail readiness. Missing `risk-based-development-flow` or `codex-ops-kit` means degraded full guardrails, not a failed OPL Flow install. Use strict mode only when a task needs to gate on the full guardrail envelope:

```bash
python3 scripts/check_companion_skills.py --strict
```

## What Gets Installed

| Layer | Entry | Installs or refreshes |
| --- | --- | --- |
| Codex workflow | `opl-flow` | `~/plugins/opl-flow`, `~/.agents/plugins/marketplace.json`, `~/.codex/AGENTS.md`, `~/.codex/TASTE.md`, and role prompts |

Key behavior after install:

- Chinese, direct, evidence-oriented communication.
- Direct / Inline / Durable task classification.
- Planner / Executor / Debugger / Verifier prompt routing.
- Risk-based verification and TDD selection.
- High-risk Codex ops routing to `codex-ops-kit`.
- Fresh evidence boundaries for runtime truth, readiness, currentness, release, CI, and owner-route claims.
- Chinese "完成度审计" for target-state delivery, anchored to the original target or plan rather than the completed slice.
- Subagent/worktree lane prompting, verification, absorption, and cleanup discipline.
- Durable writeback routing for reusable workflow lessons.
- CodeGraph marker block preservation and RTK shell preference when available.
- Compatibility with OPL App Full / Superpowers: OPL Flow routes to the execution surface already packaged by Full install and separately reports missing OPL Flow-native guardrails without failing the core profile check.

## Completion Checks

Codex should not report the setup complete until it has run the checks that apply to the chosen path:

```bash
python3 ~/opl-flow/scripts/install_local_plugin.py --verify-only
python3 ~/opl-flow/scripts/verify.py
python3 ~/opl-flow/scripts/check_companion_skills.py
```

Use `python3 ~/opl-flow/scripts/check_companion_skills.py --strict` only when claiming full guardrail readiness.

If checkout paths differ, use the actual clone location in place of `~/opl-flow`.

## Optional Repo-Native Sync

After the user-level profile is installed, a target OPL-compatible repository
can declare that it follows OPL Flow:

```bash
python3 ~/opl-flow/scripts/repo_profile.py check --repo-root /path/to/repo
python3 ~/opl-flow/scripts/repo_profile.py sync --repo-root /path/to/repo --apply
```

This writes only the workflow profile declaration and managed AGENTS/TASTE
blocks. It does not install OPL runtime modules, mutate domain contracts, or
replace repo-specific rules.

## Where This Fits

`opl-flow` configures Codex behavior on a new machine. It does not own OPL runtime, App installation, MAS/MAG/RCA domain agents, OPL App Full packaged Superpowers, or common companion skills.

`one-person-lab` is the canonical complete bootstrap owner. `one-person-lab-app` is the product and first-install owner. `opl-doc` is a domain skill for developer-document lifecycle governance.
