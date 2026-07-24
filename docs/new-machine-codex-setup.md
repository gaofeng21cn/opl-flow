# OPL Flow New Machine Setup

Owner: `gaofeng`
Purpose: `new_machine_flow_profile_setup`
State: `active_transitional_runbook`
Machine boundary: 本页给出现行可执行安装路径，并明确 target composition 边界。
命令输出、platform inventory 和 fresh executor discovery 才是本机事实。

This page installs the OPL Flow Profile only. For a complete OPL family setup,
use the canonical
[One Person Lab bootstrap guide](https://github.com/gaofeng21cn/one-person-lab/blob/main/docs/references/current-support/opl-new-machine-codex-bootstrap.md).

## Install

Current compatibility commands:

```bash
opl packages install opl-flow
opl packages update opl-flow
opl packages optimize opl-flow
```

They install the current normal Plugin identity
`opl-flow@opl-agent-opl-flow-local`, the minimal `~/.codex/AGENTS.md`,
non-runtime `~/.codex/TASTE.md`, `opl-flow`, and
`coordinate-concurrent-tasks`.

The current Framework route still performs policy migration and may produce
lock, payload, provenance, rollback receipt, or other lifecycle fields. They
are transitional implementation evidence, not target dependency requirements.

The target source is the Flow owner's per-Package GHCR
`opl-flow:latest-stable`. The shared manifest is only a
Full/offline/integration-test/QA snapshot. Base may use a thin OCI adapter and
Codex may activate Plugin/config/cache, but installation is complete only when
the carrier reports the complete Flow Package installed and the selected
executor reports the route callable.

## Dependencies

Flow dependency intent uses stable identity. `requires` means present and
callable; `recommends` means convenient by default. Neither requires SemVer/ABI
resolution, lock, payload, receipt, digest, provenance match, App, Full, or a
shared cohort.

`contracts/workflow-policy.json` still contains the current fixed companion
graph and source metadata. Framework may consume it during transition. OPL App
must not parse it or maintain a second companion list.

A missing capability remains a visible Flow-local action. It must not block
Base, App, plain Codex, Full, or unrelated Packages.

## Existing Profile

If `~/.codex/AGENTS.md` already exists, the current package route:

1. reads the original SHA;
2. creates a backup;
3. removes only known marker blocks;
4. asks for semantic preservation of distinct preferences;
5. rejects a changed target SHA;
6. validates and atomically applies the candidate.

If merge cannot be validated, the original remains unchanged and the command
returns the review/apply route. Current compatibility recovery may record a
rollback receipt; that receipt protects this user-owned file mutation only and
must not become a generic Package composition gate.

Restart the selected executor so native Plugin/Skill discovery refreshes.

## App Standard And Full

Flow may be a default root in the one App Official Profile:

- Standard installs from the online owner source.
- Full may use offline seed bytes for the same root.
- Profile application happens only at first install or explicit Restore.
- User removal persists across restart, App update, and maintenance.
- Background maintenance updates only carrier-reported installed Packages.
- App does not derive install state from its metadata or from a Codex Plugin
  list alone.

Switching from Codex CLI to another executor must preserve the installed Flow
Package, `AGENTS.md`, `TASTE.md`, user preferences, and existing tasks. Only the
new executor route may report adapter missing or unavailable.

Credentials, API keys, OAuth state, account data, and unknown user/third-party
MCP configuration are never bundled.

## Development Repositories

The installed global Profile tells Codex to initialize CodeGraph when a
development repository lacks an index:

```bash
codegraph init .
```

Git-ignore `.codegraph/`, keep a concise repo-local CodeGraph block in
`AGENTS.md`, use CodeGraph for structural search, and `rg` for literal text.

## Verification Boundary

Read current layers separately:

```bash
opl packages list --json
opl packages status --package-id opl-flow --json
codex plugin list --json
```

For repository development only:

```bash
python3 scripts/install_local_plugin.py --verify-only
```

The developer command validates a local Plugin/cache payload. It does not prove
per-Package GHCR publication, complete Package currentness, Standard/Full,
another executor, or the target migration.
