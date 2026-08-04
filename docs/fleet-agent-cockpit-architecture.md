# OPL Fleet Agent And Cockpit

Owner: OPL Flow
State: active product and protocol SSOT
Machine authority: `contracts/fleet-telemetry-protocol.json`, current source, and fresh runtime readback

Core Fleet authority: [OPL Fleet product and architecture](./opl-fleet-architecture.md)

## Product Model

This document owns Fleet's observation products and telemetry boundary. The
core product positioning, task-continuity model, execution authority, and
capability roadmap live in the Fleet architecture SSOT linked above.

OPL Fleet is one control plane with deliberately separate observation products:

| Product term | Current implementation | Responsibility |
| --- | --- | --- |
| OPL Fleet Controller | OPL Flow plus one private OPL Instance | Node registry, policy, fresh doctor/admission, leases, dispatch, and execution adapter selection |
| OPL Fleet Agent · Codex TPS | `codex-tps` | Node-local observation, doctor, execution constraints, sanitized receipts, Codex Telemetry, and the Host dashboard |
| OPL Fleet Telemetry Gateway | `ambient-ops` Docker service | Authenticated allowlisted ingest, fleet aggregation, history, and read-only status projection |
| OPL Fleet Cockpit · Ambient Ops | `ambient-ops` Web, Android, and iOS clients | Fleet/Host visualization, router network visualization, and display preferences |

The Controller is the only scheduling authority. Agent telemetry may describe
capacity or execution state, but neither the Gateway nor Cockpit may turn an
observation into admission, a lease, dispatch, or remote execution.

## Three Modes

- **Local:** the Agent reads local Codex usage and host telemetry and renders it
  locally. No telemetry upload is required.
- **Direct:** a Cockpit reads one Agent's read-only LAN endpoint. The Agent remains
  the source of that Host projection.
- **Fleet:** Agents send an allowlisted aggregate envelope to the Telemetry Gateway;
  the Cockpit reads the Gateway's Fleet and Host projections. Controller policy and
  leases remain outside this data path.

These are product modes, not competing authorities. A deployment can keep Direct
available while also reporting to a Gateway.

## Compatibility Migration

The first public names are `OPL Fleet Agent · Codex TPS` and
`OPL Fleet Cockpit · Ambient Ops`. Repository URLs, Bundle IDs, Android package
names, release asset names, update channels, `_codex-tps._tcp.local`, and
`_ambient-ops._tcp.local` remain stable. Physical repository or binary renames are
eligible only after the versioned Agent/Fleet protocol has shipped and a real
upgrade from the compatibility identities has passed.

Existing Codex TPS and Ambient Ops behavior remains supported during the migration.
New protocol fields are additive and capability-advertised before any consumer
requires them.

## Privacy And Failure Semantics

The telemetry envelope contains stable logical identity, product version, aggregate
usage, active-conversation count, host CPU/network values, capability flags, doctor
state, constraints, currentness, and sanitized receipts. It never contains prompts,
responses, conversation content, session IDs, local paths, interface names, network
addresses, credentials, secrets, or raw logs.

Nodes without fresh evidence are `stale` or `unavailable`. The Gateway and Cockpit
must not infer currentness, doctor success, lease ownership, or task completion from
an old sample. Installed binaries, release tags, and Controller receipts remain
independent terminal surfaces and require their own fresh readback.

## Dependency Direction

```text
OPL Flow public protocol and Controller engine
                +
private Instance topology and policy
                |
                v
     OPL Fleet Agent telemetry envelope
                |
        Local / Direct / Fleet
                |
                v
Telemetry Gateway -> Cockpit read-only projections
```

Codex TPS and Ambient Ops consume the public protocol. They do not duplicate the
private node registry or Controller policy. The private Instance selects approved
nodes and desired capabilities without importing public product source.
