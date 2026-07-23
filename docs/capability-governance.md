# OPL Capability Governance

Owner: `opl-flow`
Purpose: `opl_capability_graph_authority`
State: `active`
Machine boundary: `contracts/workflow-policy.json` declares the desired capability composition. Framework readback records what a particular machine resolved.

## Authority

| Layer | Owns | Must not own |
| --- | --- | --- |
| OPL Flow | Capability identity, required or recommended status, activation, source hints, conflicts, and model recommendation | Installed bytes, package locks, App payloads, user secrets, or release execution |
| OPL Base / Framework | Generic discovery, compatible-source selection, install actions, reconciliation, receipts, and projections | An OPL Flow-specific catalog or a second capability policy |
| OPL App | GUI, default package presentation, user choices, and optional distribution payloads | Dependency truth or a second Skill, Plugin, CLI, or MCP inventory |

Capability identity is `(kind, id)`. The same textual id can name different surfaces, such as `codex_skill:officecli` and `cli:officecli`.

## Open Composition

Flow states what is useful. Framework resolves it from any available compatible source:

1. Reuse an already available capability.
2. Otherwise use a declared or generally discoverable source.
3. If it is still missing, project a generic install or repair action.

A missing optional source hint is not a malformed policy. A missing installed capability is a machine state to resolve, not a reason to reject the capability graph.

`requires` means the intended Flow experience needs the capability. `recommends` means it belongs in the default convenient setup. Neither term requires a particular version, lock, carrier, or payload.

A lock records a resolution for one concrete install or release. It is not part of capability identity and is never required merely because Flow declares a dependency.

## Distribution

Standard, Full, direct Framework installation, and third-party carriers may assemble the same useful capabilities from different compatible sources and versions. They do not need byte-identical payloads or identical locks.

Full may carry capabilities that are available when it is built. Missing payloads do not invalidate Flow, Standard, Full, or App. A carrier manifest describes what that carrier actually contains; it does not become another dependency authority.

Full never bundles API keys, credentials, OAuth state, or account data. They remain user- or provider-owned. Unknown user and third-party MCP configuration is preserved.

## App Projection

App consumes Framework's unified capability projection. It may group, label, and offer user choices, but it does not infer installation state from Flow declarations or package its own mandatory dependency list.

Model selection follows:

```text
explicit user selection
> installed OPL Flow recommendation
> fresh Codex live default
> App fallback when Flow is unavailable
```

## Workflow Status Boundary

OPL Flow may define coordination semantics such as `ACTIVE` and `SAFE_TO_ARCHIVE`. `SAFE_TO_ARCHIVE` does not archive a conversation. Actual archival still requires fresh user acceptance.

## Acceptance

- Policy and schema validate.
- Provided Skills match the package manifest.
- `agent-reach` is declared as a required default Skill without a lock or payload prerequisite.
- Framework can reuse an existing compatible Skill or project a generic action when it is absent.
- App consumes Framework projection and does not own a duplicate dependency inventory.
- Published or installed artifacts use their own receipts and locks only when those artifacts actually exist.
