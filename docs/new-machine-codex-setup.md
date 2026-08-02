# OPL Flow New Machine Setup

Purpose: reusable workflow setup for a new Codex machine
State: source-implemented guided workflow
Machine boundary: commands run through each component owner; live owner and
executor readback, not this page, proves the machine state.

## Install

Install the public Codex Plugin from its owner repository:

```bash
codex plugin marketplace add gaofeng21cn/opl-flow
codex plugin add opl-flow@opl-flow-local
```

Start a new Codex task so native Skill discovery refreshes, then give one
instruction:

```text
Use $opl-flow setup to initialize my reusable development workflow.
```

The Skill performs the guided action end to end. It doctors Git, GitHub auth,
Codex, Beads, Profile, and optional Fleet/Linear; resolves one private
`opl-instance-<owner>`; initializes or bootstraps its Ledger; safely prepares
the Profile; and finishes with live readback. External repository creation and
OAuth remain explicit user-authorized actions.

Installation and `setup` deploy or repair capabilities. They do not create the
Ledger Dashboard, unique Dashboard Bead, Linear registration, or hourly
Supervisor. Formal onboarding is a separate explicit action:

```text
Use $opl-flow start to onboard my complete OPL Ledger and supervise it every hour.
```

Repeated `start` reuses the same Dashboard/Bead and the one hourly
`OPL Flow Supervisor`; installation never implies that this action ran.

For an existing OPL Framework installation, these remain supported
compatibility carrier commands:

```bash
opl packages install opl-flow
opl packages update opl-flow
```

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

Flow dependency intent uses stable identity and three independent status planes:

- `package_operational` is controlled by Flow itself plus `requires` presence
  and callability;
- `experience_baseline` is the recommended usage floor; missing capabilities
  report `degraded` and an owner-supported repair route without disabling Flow;
- `specialized_capabilities` observes optional enhancements; absence is normal
  and does not require repair.

Ordinary composition does not require an App catalog, Full build lock, or
shared release cohort. Framework may still use owner/version/readiness metadata
to materialize and diagnose a baseline capability.

`contracts/workflow-policy.json` is the default capability strategy SSOT.
Framework compiles it into online materialization, installed status,
`system_initialize.recommended_skills`, and Full build-lock projections. OPL
App must not parse it or maintain a second companion list.

A missing required capability affects only Flow's operational plane. A missing
baseline capability remains a visible repair action; a missing specialized
capability is only reported as absent. None may block Base, App, plain Codex,
Full, or unrelated Packages.

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
- Full adds only policy members marked `offline_bundle=full` and binds their
  resolved source/version/SHA-256 in a Framework-generated build lock.
- Profile application happens only at first install or explicit Restore.
- User removal persists across restart, App update, and maintenance.
- Background maintenance updates only carrier-reported installed Packages.
- App does not derive install state from its metadata or from a Codex Plugin
  list alone.
- App first-run gets recommended Skills from the installed Framework projection;
  no Flow projection means no App-invented fallback capability list.

Switching from Codex CLI to another executor must preserve the installed Flow
Package, `AGENTS.md`, `TASTE.md`, user preferences, and existing tasks. Only the
new executor route may report adapter missing or unavailable.

Credentials, API keys, OAuth state, account data, and unknown user/third-party
MCP configuration are never bundled.

## Private Instance And Ledger

The setup action reuses or clones an existing private Instance. Creating
`opl-instance-<owner>` on GitHub requires fresh confirmation of the account,
repository name, and private visibility.

A new clean primary checkout uses:

```bash
python3 scripts/opl_workflow.py ledger init --instance <opl-instance>
```

A clone of an existing Instance uses Beads' owner recovery route instead:

```bash
chmod 700 .beads
git config beads.role maintainer  # or contributor for that user's authority
bd bootstrap --yes
```

Use the Instance as the real cwd for `bd`. Pull before a coherent mutation on
another machine and push after it. Do not copy `.beads` runtime data, sessions,
credentials, or logs between machines.

## Update

On an existing machine, give one instruction:

```text
Use $opl-flow update to update this workflow from each component owner and verify it.
```

The Skill updates Flow through its carrier, Beads through its owner channel,
pulls Dolt, prepares any Profile update, reconciles declared Operations, and
checks optional Linear/Fleet only when configured. A controller's older version
never forces another machine to downgrade.

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

The public machine-readable Profile route is independent of that developer
installer:

```bash
python3 scripts/opl_workflow.py profile status
python3 scripts/opl_workflow.py profile prepare
python3 scripts/opl_workflow.py profile apply --packet <reviewed-packet>
```

`prepare` leaves an unknown existing `AGENTS.md` untouched and returns a review
packet. Only reviewed output can be applied, with stale-target and backup
guards.

## Release Qualification Boundary

Normal OPL composition is dynamic and does not lock every Package to one release
cohort. Exact version, owner commit, and GHCR digest are bound only inside the
evidence packet for the candidate currently being qualified.

Qualification has two levels. Run `python3 scripts/qualify_install.py --plan`
before each release. With no system trigger it selects `routine-release`: use
one reference platform and validate both fresh install and upgrade. The upgrade
predecessor is the real public `latest-stable` observed before candidate
promotion, not a guessed adjacent SemVer version. Routine releases still bind
the exact owner commit and GHCR digest, preserve an existing Profile or leave an
unreviewed merge packet unapplied, and read back the configured carrier.

`system-certification` is not a per-version gate. It is selected only for the
first supported release, a carrier or Package payload contract change, Profile
mutation change, executor discovery change, supported-platform change, security
boundary change, an install incident, or an explicit scheduled recertification.
It validates six sanitized live receipts: macOS, Linux, and Windows/WSL, each
in `fresh` and `upgrade` mode. Core must pass with Linear and Fleet absent, and
at least one receipt must come from a newly started Codex session that actually
invokes an installed OPL Flow Skill.

Validate the receipts with the same `--trigger` arguments used for planning.
The script selects the level; callers do not declare a second, potentially
conflicting mode. Supplying any system trigger with only routine receipts fails
closed. `codex plugin list`, an existing conversation, and repository-local
discovery are not substitutes for the new-session evidence required by system
certification. Windows Codex App mapped-home integration remains a separate
consumer qualification.
