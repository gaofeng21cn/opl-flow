# OPL App Integration

Use this reference before changing model, context, or App-facing behavior.

## Owner Split

- Flow: recommendation and reusable behavior policy.
- Framework: generic installed/callable/currentness projection and actions.
- App: product contract, UI, Auto model algorithm, fallback, user selection,
  persistence, and first-run experience.
- Shell: implements the App contract; it must not create a second policy list.

## Context Boundary

`opl_flow_context` is metadata describing an installed Flow policy. It is not a
prompt body and must be attached only when fresh package projection says
`opl-flow` is installed. Flow absence means omit the metadata.

`preset_context` belongs to a selected assistant/package or to explicit user
additional instructions. App/Shell must not synthesize a hidden Flow base
prompt, copy `AGENTS.md` into every request, or use Flow context as an agent
routing fallback.

The user's additional-instructions field remains user-owned. Empty means inject
nothing. Reset clears only that field.

## App Consumption

App consumes Framework's generic package projection. It may display:

- package operational status;
- experience-baseline status and repair action;
- specialized capability availability.

It must not parse `workflow-policy.json`, maintain a second companion list,
resolve Skill source ownership, or infer installed truth from a static contract.

Model and reasoning controls remain visible and user-selectable. Flow supplies
the recommendation; App controls Auto resolution and fallback when Flow is
absent.

## Decision Dashboard MiniApp (Standard MCP App)

OPL Flow exposes a unified Chinese decision surface across both the shared OPL Apps
catalog and a dedicated standard MCP App (`ui://opl-flow/decision-dashboard.html`):

- **Shared OPL Apps declaration**: `opl-package.json` declares `ui.declarative`,
  `ui.mcp_apps`, `provides.mcp_servers`, and `provides.contribution_handler` backed by
  `scripts/opl_app_contribution.py`.
- **Dedicated MCP App**: `mcp.json` (referenced by `.codex-plugin/plugin.json`) launches
  the bundled Node stdio MCP server `decision-dashboard/server.bundle.mjs`, serving
  `decision-dashboard/index.html` using the pinned official DSH stylesheet (`dsh-theme.css`)
  and `@modelcontextprotocol/ext-apps`.
- **Authority boundary**: the UI renders sanitized owner readback (`needs_action`,
  `safe_to_archive`, `active_objectives`, `blocked`, `backlog`, `pending_events`, and
  Router service status) and delegates writes (`send`, `approve`, `tick`, `service`)
  exclusively to `scripts/opl_app_contribution.py`. Archive approval and Router engine
  start/stop always require explicit human confirmation and fresh owner readback.
