# OPL Flow Active Truth

Date: 2026-08-02
State: source implementation; publication and installation are separate,
unauthorized terminal states.

## Product Position

OPL Flow is the optional Codex experience baseline and work-coordination
control layer. It owns the default Codex working strategy, not Codex reasoning
itself and not App UI state.

The primary Skill is a progressive router with six actions:
`doctor/setup/tune/update/start/fleet`. Installation deploys capability only;
only explicit `$opl-flow start` performs Ledger/Supervisor onboarding.

## Capability Authority

The source architecture is:

```text
OPL Flow workflow-policy.v4
  -> OPL Framework capability compiler
     -> online materialization/repair plan
     -> installed status projection
     -> system initialize recommended_skills
     -> Full capability build lock
        -> OPL App first-run/status/Full assembly
```

Flow owns identity, grouping, default intent, model recommendation,
criticality, source owner, degradation semantics, online install intent, and
Full selection. Framework owns generic validation, materialization, owner
adapters, health, status, and build-lock generation. App consumes those
projections and no longer owns a default Skill/Tool inventory or a Flow policy
parser.

See [Capability Governance](./capability-governance.md) for the full SSOT.

## Current Source Contract

`contracts/workflow-policy.json` v4 declares:

- six Flow-owned core Skills;
- required `opl-base` for Flow's own operational plane;
- four repairable, non-blocking experience bundles: internet research, Office
  authoring, document extraction, and visual design;
- two observe-only optional bundles: architecture enhancement and the official
  Codex Office runtime;
- Agent Reach Skill + CLI/doctor as the internet-research baseline;
- Full offline selection only for `cli:officecli` and
  `cli:mineru-open-api`;
- `gpt-5.6-sol + max` as the Flow recommendation, below explicit user choice.

Status remains three independent planes:

- `package_operational`;
- `experience_baseline`;
- `specialized_capabilities`.

Agent Reach or another baseline item may degrade the second plane without
disabling the first.

## Core And Enhancements

Flow bundles `opl-flow`, `coordinate-concurrent-tasks`,
`develop-and-deliver`, `recover-codex-tasks`, `task-mode-gate`, and
`opl-fleet`.

OPL Skills is optional. Catalog groups do not define a default install. The
named `development-complete` preset explicitly combines the architecture and
development methods with all six `book-*` architecture lenses. Flow passes
exact IDs and never uses a wildcard.

## Ledger And Fleet

`OPL Ledger` is the current owner/Instance's complete human work ledger, not
the Supervisor and not only OPL source development. One hourly
`OPL Flow Supervisor` may supervise multiple registered Linear projects. The
default registration is `OPL Ledger`; `codex-ready` is compatibility-only and
`codex-paused` is the dispatch opt-out. Authorized user comments are consumed
by ID exactly once through the official Linear Connector.

Ambient Ops is an OPL Fleet observability extension in the same Ledger and
Supervisor. Fleet topology, credentials, and node policy remain private
Instance state.

## App And Full Behavior

App gets recommended Skills from Framework's installed Flow projection. If
Flow is absent, App uses its product fallback and does not invent Flow policy.

Standard may materialize online-default baseline capabilities. Full uses the
same Official Profile and adds only Flow-selected offline seeds. Its
`opl_flow_capability_build_lock.v1` binds the Flow strategy digest and every
selected payload's source ref, version, and SHA-256. App rejects unknown,
missing, duplicate, drifted, and unselected managed payloads.

## Not Claimed

This source state does not by itself prove:

- an OPL Flow release or GHCR publication;
- installation into the user's current Codex home;
- an OPL App Standard or Full release;
- effective Agent Reach/channel readiness on a machine;
- `$opl-flow start` onboarding or runtime Linear/Beads/Automation mutation.

Those outcomes need separately authorized owner operations and fresh terminal
readback. This development objective performs none of them.

## Release Qualification

Routine releases use one reference platform and both fresh-install and public
predecessor-upgrade paths. Changes to Package payload, Profile mutation,
executor discovery, supported platform, or security boundary trigger system
certification instead.

The 0.1.30 capability strategy, core Skill, Fleet, Profile, and onboarding
changes cross those boundaries. A future publication must qualify the exact
immutable 0.1.30 bytes; prior 0.1.29 evidence cannot be inherited.

## Repository Verification

```bash
scripts/verify.sh full
python3 /Users/gaofeng/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .
git diff --check
```

Cross-repository delivery additionally requires Framework compiler/materializer
tests, App projection/build-lock tests, canonical `main` parity, and owner-native
worktree lifecycle cleanup.
