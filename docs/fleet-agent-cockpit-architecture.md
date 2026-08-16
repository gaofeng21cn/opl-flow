# OPL Fleet Agent And Cockpit

Owner: `OPL Flow`
Purpose: `fleet_observability_architecture`
State: `active_product_protocol_ssot`
Machine boundary: `contracts/fleet-telemetry-protocol.json`, current source, and
fresh runtime readback own effective protocol and product behavior.

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

## Capability Provider Boundary

The Fleet Agent remains a native process. Its Capability Package contributes a
discoverable, typed, read-only provider to the Framework Host; it does not move
process startup, shutdown, updates, local state, or collection into Cordis. The
provider ABI is `opl-fleet-agent.capabilities@1.0.0`, and its response shape is
owned by `contracts/fleet-agent-provider.schema.json`.

| Provider read | Stable ref | Projection status |
| --- | --- | --- |
| Local aggregate telemetry (`1m`/`5m` token and request rates) | `fleet.agent.telemetry.v1#local` | `projected` |
| Current local doctor observation | `fleet.agent.doctor.v1#current` | `projected` |
| Execution constraints | no provider ref | `not_projected` until a real caller proves a contract |
| Execution receipts | no provider ref | `deferred` until a real caller proves a contract |

Both reads are `observation_only`. They cannot issue or imply an admission
decision, lease, dispatch, completion verdict, or native lifecycle action. A Host
adapter may validate and project the response, while the native Agent remains the
source of the observation and the platform remains the process lifecycle owner.

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

The broader telemetry envelope contains stable logical identity, product version,
aggregate usage, active-conversation count, host CPU/network values, capability
flags, doctor state, constraints, currentness, and sanitized receipts. The
Capability Provider projects only aggregate telemetry and doctor observations;
constraints are `not_projected` and receipts are `deferred`. Neither surface ever
contains raw prompts, responses, content, session IDs, local paths, interfaces,
addresses, credentials, secrets, or raw logs.

Every provider response carries `fresh`, `stale`, or `unavailable` plus an explicit
`last_observed_at` and `last_known` value. A stale response is always last-known,
never current. The top-level `observed_at` records the read attempt even when the
native carrier is unavailable; `native_carrier.availability` and `.status` report
that carrier result independently from observation freshness.

When an unavailable carrier has no prior observation, `node` is `null`; telemetry
rates and host metrics are `null`, and doctor state is `unavailable`. Implementations
must not invent a node ID, Agent version, zero metrics, or healthy doctor result as a
sentinel. When a prior observation exists, `last_known=true`, `last_observed_at`
identifies that sample, and its node and payload may be projected as last-known.
The Gateway, Host adapter, and Cockpit must not infer currentness, doctor success,
lease ownership, or task completion from that old sample. Installed binaries,
release tags, and Controller receipts remain independent terminal surfaces and
require their own fresh readback.

## Dependency Direction

```text
OPL Flow public protocol and Controller engine
                +
private Instance topology and policy
                |
                v
OPL Fleet Agent native process and provider
       |                         |
       | provider ABI            | telemetry envelope
       v                         v
Framework Host adapter   Local / Direct / Fleet
                                 |
                                 v
                  Telemetry Gateway -> Cockpit
```

Codex TPS and Ambient Ops consume the public protocol. They do not duplicate the
private node registry or Controller policy. The private Instance selects approved
nodes and desired capabilities without importing public product source.
