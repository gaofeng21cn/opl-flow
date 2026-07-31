# OPL Reusable Development Workflow Architecture

Owner: `OPL Flow`
State: `target architecture and migration authority`
Scope: product names, module ownership, repository boundaries, private-instance
boundaries, onboarding, and migration order for the reusable development
workflow.

This document is the SSOT for the reusable workflow system. Package/carrier/
executor composition remains owned by
[Capability governance](./capability-governance.md). Current installed behavior,
repository bytes, and machine state remain proven only by their contracts,
source, owner surfaces, and fresh readback.

## One Product

Users install and understand one product: **OPL Flow**.

OPL Flow keeps Codex model-native:

- Codex owns task decomposition, task creation, agent execution, conversation
  coordination, and recovery.
- **OPL Ledger** uses Beads only as the durable task ledger. It does not replace
  Codex scheduling or dispatch agents.
- **OPL Fleet** supplies optional multi-machine enrollment, capability
  reconciliation, repository currentness, admission, and dispatch.
- Linear is an optional human intake and visibility adapter. It is not the
  execution or ledger authority.
- Gas City/Gas Town is not part of the supported architecture.

## Product And Repository Names

| Product term | Target physical owner | Role |
| --- | --- | --- |
| **OPL Flow** | `gaofeng21cn/opl-flow` | Single public product, Codex Plugin/Profile, bootstrap, doctor, core workflow Skills, Ledger adapter, Git lifecycle, and Fleet engine |
| **OPL Ledger** | OPL Flow module backed by Beads | Dynamic Program, slice, dependency, owner, task, checkpoint, and remaining state |
| **OPL Fleet** | OPL Flow module | Multi-machine join, capability parity, repository currentness, lease/admission, and optional dispatch |
| **OPL Skills** | `gaofeng21cn/opl-skills` | Optional, independently installable public enhancements |
| **OPL Instance: `<owner>`** | one private repository per owner; for this owner `gaofeng21cn/opl-instance-gaofeng` | Private Ledger data, Fleet nodes/policy, repository governance, private overlays, personal Skills, and sanitized receipts |
| **OPL Personal Skills** | `skills/` inside the owner's OPL Instance | Private or personal Skill source; not a separate user-facing product |

The GitHub repository renames to `opl-skills` and `opl-instance-gaofeng`
completed on 2026-07-31. The old names remain permanently reserved and are not
canonical URLs. This physical rename does not prove authority consolidation:
generic Fleet code, private instance data, contracts, installed routes, and
live nodes move only through the remaining migration and readback gates below.

## Authority Layout

The target public repository stays shallow while the codebase is small:

```text
opl-flow/
|-- .codex-plugin/
|-- profile/
|-- skills/
|   |-- opl-flow/
|   |-- coordinate-concurrent-tasks/
|   |-- develop-and-deliver/
|   |-- task-mode-gate/
|   `-- recover-codex-tasks/
|-- modules/
|   |-- ledger/
|   `-- fleet/
|-- scripts/
|-- contracts/
|-- docs/
`-- tests/
```

Do not split `modules/` into separately published packages until independent
versioning or consumers prove that need.

Each user gets one private instance:

```text
opl-instance-<owner>/
|-- .beads/                    # durable dynamic task ledger
|-- fleet/                     # nodes, policy, assets, sanitized receipts
|-- governance/                # durable repository/account policy
|-- profile/                   # private overlays
`-- skills/                    # OPL Personal Skills
```

Never commit credentials, tokens, SSH routes, lease nonces, local absolute
paths, sessions, histories, logs, caches, runtime databases, or exhaustive
machine state. Those remain in the OS credential owner, `~/.config/opl-flow/`,
or `~/.local/state/opl-flow/` with restrictive permissions.

## Ledger And Governance

The private instance contains related but distinct authorities:

| Authority | Change rate | Owns | Does not own |
| --- | --- | --- | --- |
| OPL Ledger / Beads | frequent | objectives, slices, dependencies, task/thread references, checkpoints, remaining work | repository policy, machine mutation, agent dispatch |
| Repository Governance | infrequent | active repositories, visibility, CI tier, default branch, review triggers | task progress, Fleet execution |
| OPL Fleet state | periodic | approved nodes, capability policy, sanitized readback | task truth, source code authority |

OPL Fleet may consume Repository Governance to discover approved repositories.
It must not rewrite governance policy as a side effect of synchronization.
Repository policy changes remain explicit owner actions.

## Developer Workflow

1. The developer validates personal workflow changes first in the effective
   local `~/.codex/AGENTS.md`.
2. Codex creates and coordinates tasks natively. OPL Ledger persists only the
   durable graph and recovery facts.
3. Git work proceeds in task-owned worktrees. Overlap is an integration risk,
   not a development-time global lock.
4. Owners push recoverable task checkpoints and replay against fresh
   canonical `main` before integration.
5. Only proven reusable behavior is promoted into OPL Flow.
6. After an OPL Flow release, each Fleet node updates from component owners and
   proves installed behavior by fresh readback.

## Development Repository Currentness

Every managed node uses `~/workspace` (or an explicit absolute
`OPL_WORKSPACE`) as its development root. Repository bytes always come from the
repository's official Git remote, never from another Fleet node.

The repository reconciliation invariant is:

1. discover existing first-level Git checkouts with a GitHub remote belonging
   to the configured owner;
2. use the current branch's configured Git upstream as the authority and run
   `git fetch --prune <remote>`; report a missing upstream instead of guessing;
3. update only a clean checkout on its default branch with
   `git merge --ff-only origin/<default>`;
4. never reset, rebase, merge, switch, or delete a dirty checkout, task branch,
   detached checkout, local-ahead branch, or diverged branch;
5. report those states for the owning task to checkpoint or integrate;
6. run at node reconciliation, before development dispatch, and on explicit
   operator request.

This keeps clean canonical checkouts current while preserving independent
multi-machine work. Fleet synchronization cannot replace the task owner's duty
to push checkpoints and integrate against fresh canonical SSOT.

During migration the executable surface is:

```bash
codex-fleet repos status
codex-fleet repos sync
```

The target public surface is `opl-flow fleet repos ...`.

## Public Onboarding

The public entry remains the Codex-native carrier:

```bash
codex plugin marketplace add gaofeng21cn/opl-flow
codex plugin add opl-flow@opl-flow-local
```

The target first-session action is:

```text
Use $opl-flow setup to initialize this development workflow.
```

`setup` must:

1. doctor Codex, Git, GitHub authentication, and Beads;
2. install missing dependencies only through owner-supported channels;
3. create or connect one private OPL Instance;
4. initialize Beads without overwriting `AGENTS.md` or Git hooks;
5. back up and safely merge the OPL Flow Profile;
6. optionally connect Linear;
7. optionally enroll Fleet nodes through outbound authentication;
8. finish with live readback.

Only OAuth or owner-required authorization remains interactive. Core setup must
not require OPL App, a continuously running controller, inbound SSH, Linear, or
Fleet.

## Migration

### Phase 0: Architecture And Facade

- Publish this SSOT and brand vocabulary.
- Add the safe repository-currentness surface to the existing Fleet engine.
- Keep all current repository URLs and runtime owners valid.

### Phase 1: Unified OPL Flow Entry

- Add `$opl-flow setup`, `status`, and `update`.
- Add a ledger-only Beads adapter and pilot one Program in shadow mode.
- Expose existing Fleet behavior through the OPL Flow entry without moving
  implementation yet.

### Phase 2: Authority Consolidation

- Move the generic Fleet engine and `codex-machine-sync` behavior into OPL
  Flow.
- Move workflow-coupled Skills into OPL Flow.
- Move Fleet private data, Repository Governance, private overlays, personal
  Skills, and Beads data into `OPL Instance: Gaofeng`.
- Keep OPL Skills only for optional, independently useful public enhancements.
- Maintain exactly one active source owner for every Skill and contract during
  transfer.

### Phase 3: Physical Rename And Retirement

- **Completed 2026-07-31:** rename `codex-skills-public` to `opl-skills` and
  `codex-skills-private` to `opl-instance-gaofeng`, with the GitHub Repository
  Governance owner performing the physical mutation and remote readback.
- Keep source constants, schemas, validators, tests, presets, installer routes,
  local remotes, and live node routes on the new canonical names. Do not leave
  machine-readable contracts dependent on redirects.
- Treat the GitHub Repository Governance task as the sole writer for GitHub
  rename, redirect, topics, settings, Actions, and owner-authoritative remote
  readback; OPL Flow supplies the source checkpoint and expected mapping.
- Update Git remotes, raw/API URLs, installer commands, manifests, workflows,
  docs, `skill-reference`, management boundaries, repository governance,
  skill-authority contracts, validators/tests, `codex-machine-sync` presets,
  installed runtime projections, node control checkouts, and local directory
  names.
- Permanently reserve the old repository names and never reuse them. Verify
  GitHub redirects as a temporary compatibility check, but immediately update
  every canonical URL, local remote, and managed caller to the new names;
  redirects are never an authority or long-term dependency.
- Re-audit GitHub-hosted Actions, Pages, releases, deployments, hooks,
  environments, secrets, and variables immediately before rename. GitHub
  Action references hosted inside a renamed repository do not follow repository
  redirects. The current two source repositories expose none of those surfaces
  and are not Action sources, so they do not require old-name shim repositories.
- Retire transitional layouts and compatibility references only after all
  generic and personal authorities have moved and live nodes use the new
  routes. Repository rename completion alone does not satisfy this gate.

### Phase 4: Release Qualification

- Test fresh and upgrade installs with temporary homes on macOS, Linux, and
  Windows/WSL.
- Verify Core without Linear or Fleet, then the optional adapters.
- Publish one OPL Flow release and perform live node readback.

## Maintainer Surface

The maintainer releases:

1. OPL Flow: product code, schemas, migrations, core Skills, bootstrap, doctor,
   and compatibility tests.
2. OPL Skills: optional enhancements on their own cadence.
3. OPL Instance: private data and policy changes, never public product code.

External dependencies use minimum compatible capabilities rather than pinning
every node to the controller's older version. Each node installs or upgrades
from the component owner and records the observed version.

## Completion Criteria

The consolidation is complete only when:

- a new user can install OPL Flow and initialize Core through one guided action;
- one private instance contains the durable Ledger and private policy;
- public workflow behavior has one source owner in OPL Flow;
- OPL Fleet is usable without understanding a separate public repository;
- OPL Skills is optional;
- every renamed remote and installed node reads back the new canonical owners;
- old repositories contain no unique authority and can be archived without
  losing source, state, or recovery evidence.
