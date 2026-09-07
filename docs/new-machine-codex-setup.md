# OPL Flow New Machine Setup

This runbook installs and verifies a machine through the current component
owners. [Capability governance](capability-governance.md) owns the architecture;
the commands and fresh carrier/executor readback establish machine state.

## Install And Discover

For an existing Framework installation:

```bash
opl packages install opl-flow --json
```

The public native Codex Plugin entry is:

```bash
codex plugin marketplace add gaofeng21cn/opl-flow
codex plugin add opl-flow@opl-flow
```

Use the configured carrier route rather than installing a second copy. Start a
new Codex task when discovery needs refreshing and verify that `opl-flow`,
`software-development`, and `manage-codex-tasks` are available. A native Plugin
listing alone does not prove Framework Package or Profile currentness.

## Establish The Baseline

```text
Use $opl-flow setup to establish or repair my Codex baseline.
```

The [setup procedure](../skills/opl-flow/references/setup-update.md) reads the
configured Framework/carrier state, prepares the Profile, and repairs declared
capabilities through their owners. It resolves private Ledger/Fleet state only
when requested. A missing baseline capability is a non-blocking degraded
experience; an absent optional enhancement needs no repair.

Existing user Profile content uses Framework's backup, semantic preservation,
stale-target check, validation, atomic write, and readback. If a candidate
cannot be validated, the original stays unchanged and the action returns the
review/apply route. Do not replace it with a repository-local installer.

## Enable Durable Work

Core setup does not create the Dashboard, its Bead, Linear registration, or an
Automation. To request that onboarding explicitly:

```text
Use $opl-flow start to onboard my OPL Ledger and supervise it every hour.
```

[Ledger start](../skills/opl-flow/references/ledger-start.md) owns the procedure
and its acceptance. It reuses the unique Dashboard, Bead, registered Linear
projection, and one `OPL Flow Supervisor`; repeating it must not create duplicates.
Resolve a private Instance first. Create a remote repository only with the
user's authorization for its owner, name, and private visibility.

New Ledger initialization runs in a clean primary checkout:

```bash
python3 scripts/opl_workflow.py ledger init --instance <opl-instance>
```

A clone of an existing Ledger instead runs the owner recovery route from that
Instance checkout:

```bash
chmod 700 .beads
git config beads.role maintainer
bd bootstrap --yes
```

Choose `contributor` instead of `maintainer` when that is the user's authority.
Use the Instance as the `bd` working directory. Pull before a coherent mutation,
push afterward, then read back parity. Do not copy runtime databases,
credentials, sessions, or logs between machines.

## Update And Verify

```text
Use $opl-flow update to update the configured workflow from its component owners and verify it.
```

The operation uses Framework for Flow and Profile updates, each external owner
for its capabilities, and direct Dolt commands when the environment uses a
Ledger. It does not run `start` or force nodes to match an older controller.

Read the applicable layers separately:

```bash
opl packages list --json
opl packages status --package-id opl-flow --json
codex plugin list --json
python3 scripts/opl_workflow.py status --instance <opl-instance>
```

The last command requires a configured Instance. Verify callability in a new
executor when discovery changed. Neither source tests nor an existing task
proves effective installation. Source maintainers use `scripts/verify.sh`;
publishing follows the separate
[Package release procedure](../skills/opl-flow/references/package-release.md).

## Optional Fleet

Enroll or reconcile nodes only when remote work is requested, using the
[Fleet guide](../skills/opl-flow/references/fleet/guide.md). Each node installs
from component owners. Workspace/currentness, fresh admission, leases, and
execution readback are required by that route; a connected node or lease is
not a completed task.
