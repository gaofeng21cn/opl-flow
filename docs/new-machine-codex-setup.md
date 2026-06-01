# New Machine Codex Setup

Owner: `gaofeng`
Purpose: `new_machine_codex_opl_bootstrap_entry`
State: `active`
Machine boundary: Human-readable bootstrap runbook. The executable truth remains each repository installer, App release asset, OPL CLI output, Codex plugin registry, and repo-native verification command.

Use this page as the GitHub entry point for asking Codex to configure a new machine with the OPL workflow, documentation governance, App/runtime payloads, and family agent surfaces.

## Copy This Into Codex

```text
请按 OPL Flow 帮我完成这台新机器的 OPL 全家桶安装配置。

Source of truth:
- OPL Flow: https://github.com/gaofeng21cn/opl-flow/blob/main/docs/new-machine-codex-setup.md
- OPL App install entry: https://github.com/gaofeng21cn/one-person-lab-app
- OPL Framework: https://github.com/gaofeng21cn/one-person-lab
- OPL Doc: https://github.com/gaofeng21cn/opl-doc

目标:
1. 安装并验证 OPL Flow，让 Codex 获得用户级 AGENTS.md、TASTE.md、planner/executor/debugger/verifier 角色库和 opl-flow 插件。
2. 安装并验证 OPL Doc，让 Codex 获得 opl-doc 与 opl-doc-governance 兼容 skill，以及 opl-doc-doctor。
3. 安装或打开 One Person Lab App；首次安装 macOS Apple Silicon 时优先使用 Full DMG，CLI 路径可使用 App 仓库 install.sh。
4. 安装或刷新 OPL Framework CLI 后运行 opl skill sync，让 MAS/MAG/RCA 作为 plugin-packaged domain skills，OMA 作为 OPL-generated skill surface 可见。
5. 完成后报告安装路径、验证命令输出摘要、仍需人工处理的权限或网络问题。

约束:
- 修改前读取当前机器已有 ~/.codex、~/.agents/plugins/marketplace.json、~/plugins 和 OPL 相关 checkout 状态。
- 不覆盖用户已有配置；若安装器会替换用户级 profile，确认其备份路径。
- 不把 MAS/MAG/RCA 镜像成重复的 ~/.codex/skills/{mas,mag,rca} 裸 skill。
- 不把 Codex plugin 当成第二套语义；domain skill 仍是 MAS/MAG/RCA 的公共 ABI。
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

### 2. OPL Doc

OPL Doc owns the OPL-native developer-document lifecycle skill and read-only doctor.

```bash
git clone https://github.com/gaofeng21cn/opl-doc.git
cd opl-doc
python3 scripts/install_local_plugin.py
python3 scripts/install_local_plugin.py --verify-only
```

This installs the canonical `opl-doc` skill and keeps `opl-doc-governance` only as a compatibility skill entry.

### 3. One Person Lab App And Runtime

For a first-time macOS Apple Silicon user, install the latest Full first-install DMG from:

https://github.com/gaofeng21cn/one-person-lab-app/releases/latest

Choose:

```text
One-Person-Lab-Full-<version>-mac-arm64.dmg
```

The Full package is the product path for a clean machine. It includes the desktop App, OPL Framework runtime payloads, Foundry Agents, current runtime payloads, `officecli`, and recommended skill payloads.

For terminal-driven setup, the App repository also exposes the one-shot installer:

```bash
curl -fsSL https://raw.githubusercontent.com/gaofeng21cn/one-person-lab-app/main/install.sh | bash
```

Use the complete terminal path when a full framework/module install is explicitly wanted from the shell:

```bash
curl -fsSL https://raw.githubusercontent.com/gaofeng21cn/one-person-lab-app/main/install.sh | bash -s -- --complete
```

### 4. OPL Framework And Agent Surfaces

After OPL CLI is available, verify the framework and sync Codex-visible agent surfaces:

```bash
opl help --text
opl modules
opl skill sync
opl system initialize --json
```

The important boundary is:

- MAS, MAG, and RCA are plugin-packaged domain skill entries.
- OPL Meta Agent is an OPL-generated skill surface.
- `opl skill sync` is the unified sync command.
- MAS/MAG/RCA must not also appear as duplicate bare skills under `~/.codex/skills/{mas,mag,rca}`.

## What Gets Installed

| Layer | Entry | Installs or refreshes |
| --- | --- | --- |
| Codex workflow | `opl-flow` | `~/plugins/opl-flow`, `~/.agents/plugins/marketplace.json`, `~/.codex/AGENTS.md`, `~/.codex/TASTE.md`, and role prompts |
| Docs governance | `opl-doc` | `~/plugins/opl-doc`, `opl-doc`, `opl-doc-governance` compatibility skill, and `~/.local/bin/opl-doc-doctor` |
| Product/runtime | `one-person-lab-app` | Desktop App, Full first-install payloads, updater surface, user guides, first-run checks |
| Framework/agents | `one-person-lab` | `opl` CLI, runtime initialization, module discovery, `opl skill sync`, App-readable state/action surfaces |

## Completion Checks

Codex should not report the setup complete until it has run the checks that apply to the chosen path:

```bash
python3 ~/opl-flow/scripts/install_local_plugin.py --verify-only
python3 ~/opl-flow/scripts/verify.py
python3 ~/opl-doc/scripts/install_local_plugin.py --verify-only
opl help --text
opl skill sync
opl system initialize --json
```

If checkout paths differ, use the actual clone locations in place of `~/opl-flow` and `~/opl-doc`.

For App installation, completion evidence is either a successful first launch reaching Core readiness in the App or a clear blocker from the App first-run page / installer output.

## Where This Fits

`opl-flow` is the canonical entry for configuring Codex behavior on a new machine. It can point Codex to `opl-doc`, `one-person-lab-app`, and `one-person-lab`, but it does not own their runtime truth.

`one-person-lab-app` is the product and first-install owner. `one-person-lab` is the framework/runtime and agent sync owner. `opl-doc` is a domain skill for developer-document lifecycle governance.
