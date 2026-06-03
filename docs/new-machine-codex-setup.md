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

OPL Flow owns the Codex-side working profile: user-level `AGENTS.md`, `TASTE.md`, role prompts, subagent contract, Durable writeback, and completion verification.

```bash
git clone https://github.com/gaofeng21cn/opl-flow.git
cd opl-flow
python3 scripts/install_local_plugin.py
python3 scripts/install_local_plugin.py --verify-only
python3 scripts/verify.py
```

If the machine already uses SSH keys for GitHub, the clone URL can be `git@github.com:gaofeng21cn/opl-flow.git`.

Restart Codex after installation so plugin and skill discovery refresh.

## What Gets Installed

| Layer | Entry | Installs or refreshes |
| --- | --- | --- |
| Codex workflow | `opl-flow` | `~/plugins/opl-flow`, `~/.agents/plugins/marketplace.json`, `~/.codex/AGENTS.md`, `~/.codex/TASTE.md`, and role prompts |

## Completion Checks

Codex should not report the setup complete until it has run the checks that apply to the chosen path:

```bash
python3 ~/opl-flow/scripts/install_local_plugin.py --verify-only
python3 ~/opl-flow/scripts/verify.py
```

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

`opl-flow` configures Codex behavior on a new machine. It does not own OPL runtime, App installation, MAS/MAG/RCA domain agents, or OPL companion skills.

`one-person-lab` is the canonical complete bootstrap owner. `one-person-lab-app` is the product and first-install owner. `opl-doc` is a domain skill for developer-document lifecycle governance.
