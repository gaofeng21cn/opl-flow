# OPL Capability Governance

Owner: `opl-flow`
Purpose: `opl_capability_graph_authority`
State: `active`
Machine boundary: `contracts/workflow-policy.json` is the declaration authority. Framework package locks, lifecycle receipts, currentness readback, and Codex discovery are the execution evidence.

## Authority

| Layer | Owns | Must not own |
| --- | --- | --- |
| OPL Flow | Required capability graph, source and version requirements, default installation, activation, offline-carrier policy, conflicts, and credential policy | Installation state, package locks, user secrets, App UI state, or release execution |
| OPL Base / Framework | Install, update, rollback, release-lock resolution, currentness, reconciliation, receipts, and projections | A competing capability inventory or domain-specific capability decisions |
| OPL App | GUI, installation progress, user controls, carrier selection, and release-frozen projections | Skill, Plugin, CLI, or MCP lifecycle truth |

An internally developed capability is built into OPL Flow only when it is generic Codex workflow behavior and shares the Flow release lifecycle. Authorship alone does not make a capability built in. `opl-flow` and `coordinate-concurrent-tasks` satisfy this rule and appear under `provides`.

## Capability Identity

Capability identity is the tuple `(kind, id)`. The same textual id may identify different surfaces, such as `codex_skill:officecli` and `cli:officecli`. Policy consumers must preserve the tuple and must not collapse it into an id-only inventory.

Supported kinds are `base`, `codex_skill`, `codex_plugin`, `mcp_server`, `cli`, and `runtime_capability`. A default dependency is not considered installed or current unless Framework has a lifecycle adapter and produces the required lock and receipt. An unknown default Plugin or MCP dependency fails closed.

Each declaration records:

- owner, version requirement, and source;
- install source and lifecycle owner;
- default-install, offline-carrier, and activation policies;
- conflict and credential policies.

## Standard And Full

Standard and Full are delivery modes for one target installation, not different feature editions.

```text
standard_target_closure == full_target_closure
standard_source = online_exact_release_lock
full_source = embedded_exact_release_lock
standard_final_projection == full_final_projection
```

Every default dependency must therefore use `offline_bundle=full`. Standard resolves the release cohort's exact bytes online. Full embeds those same exact bytes and can install without network access. Final version, digest, lock, Skill/Plugin discovery, and capability projection must match at the reconciliation receipt. GUI launch alone is not proof of convergence.

Full never bundles API keys, OAuth tokens, account state, or other secrets. It may bundle public binaries and configuration templates. Credential values remain user- or provider-owned.

## Plugins And MCP

Flow may declare a Codex Plugin or MCP server through the same capability graph, but declaration does not bypass Framework lifecycle support. A default Plugin or MCP requires an exact source, release-lock resolution, install/update/rollback/currentness receipts, and a credential policy before it can enter the default closure.

Flow-managed MCP surfaces are projected separately from user-managed and third-party MCP surfaces. Reconciliation preserves unknown user surfaces and never copies, deletes, or overwrites their credentials merely because they are absent from Flow policy.

No external default MCP server is declared in the current policy. The v2 type exists so a future dependency must satisfy these requirements before installation is allowed.

## App Projections

App Settings consumes Framework's unified capability projection. It may group managed, manual, and third-party capabilities, but it must not maintain a second managed inventory.

The App Full third-party source manifest is a release-frozen projection generated from the selected Flow policy plus Base/Framework toolchain closure. It binds exact refs, digests, and receipts for reproducibility; it is not dependency lifecycle authority.

Model selection follows:

```text
explicit user selection
> installed OPL Flow recommendation
> fresh Codex live default
> App fallback when Flow is unavailable
```

The App fallback is availability behavior only and never competes with an installed Flow recommendation.

## Workflow Status Boundary

OPL Flow may define coordination semantics such as `ACTIVE` and `SAFE_TO_ARCHIVE`. `SAFE_TO_ARCHIVE` authorizes title and evidence updates only. Actual conversation archival requires fresh user acceptance for the named task or thread. Git, package, install, release, and archive mutation permissions remain with their owning surfaces.

## Acceptance

A release closes this boundary only when all of the following are true:

- policy and schema validate, and provided Skills exactly match the package manifest;
- Standard and Full resolve the same default `(kind, id)` closure and exact release lock;
- every managed dependency has install, update, rollback, and currentness evidence;
- Full embedded bytes match the release lock without bundled secrets;
- Framework readback is current and App has no second managed inventory;
- fresh Codex discovery reports the packaged Plugin and every required Skill.
