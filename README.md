# OPL Flow

OPL Flow distributes a minimal, model-native preference profile. It is an OPL
Package whose capabilities include the user-level `AGENTS.md`, non-runtime
`TASTE.md`, the `opl-flow` skill, and the bounded
`coordinate-concurrent-tasks` skill.

Flow is optional. OPL App may include it as a default root in the App Official
Profile, but Flow is not a readiness prerequisite for OPL Base, OPL App,
Standard, Full, ordinary Codex, another Package, or a domain Agent.

## Public Boundary

The ecosystem model is:

```text
OPL Base        ~= R
OPL App         ~= RStudio / replaceable GUI and deployment carrier
OPL Package     ~= R Package
OPL Flow        = OPL Package(kind=workflow_profile)
```

Package, carrier, and executor are independent:

```text
Package  = stable identity, capabilities and dependency intent
Carrier  = GHCR/Git/Codex Plugin Manager/OS or local platform
Executor = Codex CLI/Claude Code/Hermes Agent/future route
```

Codex Plugin Manager is the first Flow carrier adapter, not Flow's identity or
installed truth. Codex CLI is the current first executor. Changing executor
must not reinstall Flow or discard the user's Profile, preferences, or existing
task state.

For the complete ownership, GHCR, dependency, App, Full, Profile-safety, and
migration boundary, use
[OPL Flow Composition Architecture](docs/capability-governance.md). That page is
the repository's human-readable composition SSOT.

OPL Flow does not own App readiness, Framework runtime behavior, Package
currentness, project facts, release truth, task truth, or domain acceptance.
Those claims stay with the owning platform, Package, runtime, contract, fresh
readback, or domain owner.

## Minimal Profile

The durable profile contains only:

- Chinese, conclusion-first, concise communication preferences.
- Read the effective repository, call path, repo-local instructions, contracts,
  and implementation before editing.
- Keep the user's highest-priority verifiable outcome on the critical path.
- Depend only on prerequisites that reached their authority and took effect.
- Delegate only independent critical-path work with bounded concurrency.
- Use RTK for compact shell output and native commands when fidelity matters.
- Initialize and Git-ignore `.codegraph/` in development repositories.

It does not install a planning methodology, global persona, release authority,
project truth, or companion readiness ceremony.

## Profile Source And Safety

`templates/AGENTS.md` is rendered from
`profile/modules/01-user-preferences.md`, declared by
`profile/manifest.json`:

```bash
python3 scripts/profile_compose.py write
python3 scripts/profile_compose.py check
```

The composer only renders deterministic repository bytes. Applying them to a
user-owned `~/.codex/AGENTS.md` has a deliberately narrow safety invariant:

1. read and hash the original target;
2. back it up;
3. remove only known marker blocks and preserve distinct user preferences;
4. reject a stale target whose SHA changed before apply;
5. validate and atomically replace the target.

If automatic merge cannot be validated, the original stays in place and the
current compatibility command returns
`opl packages profile-apply opl-flow --packet <path>`. This Profile-specific
backup/stale-write/atomic behavior must not grow into a generic Package
lock/payload/receipt state machine.

`~/.codex/TASTE.md` remains a human-maintained authoring source, not runtime
session input. Repo-specific facts and procedures stay repo-local.

## Install Or Update

The currently executable public compatibility route is:

```bash
opl packages install opl-flow
opl packages update opl-flow
opl packages optimize opl-flow
```

These commands still traverse the existing Framework package lifecycle. Current
contracts and code may therefore emit resolver, lock, payload, receipt,
rollback, source-provenance, or migration fields. Those fields describe the
transitional implementation; they are not target Flow composition or readiness
requirements.

The target online publication and update path is:

```text
Flow owner source/tag
  -> ghcr.io/<owner>/one-person-lab-packages/opl-flow:<immutable-tag>
  -> ghcr.io/<owner>/one-person-lab-packages/opl-flow:latest-stable
  -> thin Base OCI/native adapter
  -> carrier install/update
  -> fresh installed and executor-callable readback
```

The Flow owner advances its own `latest-stable` independently. The shared
`one-person-lab-manifest:latest-stable` is only a Full/offline/integration-test/
QA snapshot, not ordinary Flow currentness.

Codex Plugin Manager owns Codex Plugin/config/cache mechanics. Base may retain
one thin OCI download adapter because Codex does not consume GHCR OCI directly,
but it must install and read back the complete Flow Package rather than only
the Plugin subtree.

Restart the selected executor when its native discovery requires it.

## Capability Composition

Flow declares capability intent by stable `(kind, id)`. A normal required edge
means the identity must be present and callable. It does not require SemVer or
ABI solving, an exact version/digest, lock, payload, receipt, provenance match,
or a shared release cohort.

Breaking capability interfaces use a new identity or an owner-side adapter.
Missing dependencies affect Flow only; they do not make Base, App, Full, plain
Codex, or unrelated Packages unavailable.

`contracts/workflow-policy.json` is still the current executable policy and
contains a fixed capability graph plus migration metadata. It remains
transitional machine truth until dual-read migration and terminal platform
proof allow its lifecycle fields to be removed. OPL App must not parse this
file or maintain a companion Skill/Tool/Plugin/MCP list from it. App consumes
only the generic Framework projection of actual platform state.

Model precedence remains:

```text
explicit user selection
> installed Flow recommendation
> fresh executor default
> App fallback when Flow is unavailable
```

Credentials, OAuth state, account data, and unknown user or third-party MCP
configuration are never bundled or overwritten.

## Currentness And Readback

Keep these independent:

1. Owner publication: source/tag and per-Package GHCR `latest-stable`.
2. Carrier installed truth: what the actual platform reports installed and
   healthy for the complete Package.
3. Executor route: whether the selected executor can discover and call it.
4. Full/QA snapshot: the exact bytes selected for one reproducible build only.

During migration, inspect current Framework output without promoting its
lock/payload fields into composition gates:

```bash
opl packages list --json
opl packages status --package-id opl-flow --json
codex plugin list --json
```

An owner tag, a shared manifest, a clean checkout, docs, or tests do not prove
this machine installed or activated the Package.

## OPL App Standard And Full

OPL Flow can be a default root in the single App Official Profile:

- Standard installs it online; Full may use offline seed bytes.
- Both use the same desired roots.
- The Profile runs only on first install or explicit Restore.
- User removal persists across startup, App update, and silent maintenance.
- Maintenance updates only Packages still reported installed by their carrier.
- Flow failure remains local and does not block other roots.

After an App carrier changes, the current implementation may request generic Framework reconciliation
for already installed Packages. The target keeps the generic scheduling and
readback result while delegating each physical update to its platform; it never
treats Official Profile drift as reinstall permission.

## Developer Local-Source Tool

`scripts/install_local_plugin.py` is for repository development and local-source
testing only. It is not ordinary Package installation or currentness authority:

```bash
python3 scripts/install_local_plugin.py --no-profile
python3 scripts/install_local_plugin.py --verify-only
scripts/verify.sh
scripts/verify.sh full
```

Its exact Plugin/cache payload checks prove only the local development carrier.
They do not prove per-Package GHCR publication, platform installation, another
executor route, or App/Full readiness.

## Repo Profile Sync

OPL Flow can check or write only the metadata portion of an OPL-native repo
profile:

```bash
python3 scripts/repo_profile.py check --repo-root /path/to/repo
python3 scripts/repo_profile.py sync --repo-root /path/to/repo
python3 scripts/repo_profile.py sync --repo-root /path/to/repo --apply
```

`sync` is dry-run unless `--apply` is present. Apply updates
`contracts/opl-native-profile.json` and removes known legacy Flow marker blocks.
Repo-local instructions remain repository-owned.

## Usage

Ask Codex:

```text
Use OPL Flow for this task.
```

The minimal profile acts as preferences, not a task router. Ordinary reasoning
remains model-native; specialist skills load only through their own triggers.

For several active tasks:

```text
Use $coordinate-concurrent-tasks to rebuild the active execution graph, run
independent work in parallel, integrate against fresh SSOT, and mark completed
tasks SAFE_TO_ARCHIVE without archiving them before my review.
```

The skill coordinates existing owners. It cannot create release/package
authority, authorize Git mutation, or archive a task without fresh user
acceptance.

## Compatibility With OPL App Full

Full is an optional offline carrier for the same App Official Profile. It is not
a second Flow edition, dependency authority, or update channel. Missing embedded
Flow bytes do not invalidate Base/App; Full must report the root failure
locally. Once online, the installed Package follows its owner
`latest-stable`, independently of the frozen Full snapshot.

The target migration is incomplete until clean Standard and Full installs,
remove-without-reinstall, owner-independent update, Profile safety, full
Package readback, and executor-switch preservation all have fresh terminal
proof. Current machine contracts remain authoritative until then.

## Relationship To OPL Doc

OPL Doc is a separate developer support repository for OPL-family documentation
governance. It is not a normal-user dependency of OPL Flow or OPL Base.

OPL Flow owns only its metadata entry in a consumer repo's
`contracts/opl-native-profile.json`; repo-local `AGENTS.md` and project truth
remain with that repository. This source repo intentionally has no self-owned
`contracts/opl-native-profile.json`.

## Development

```bash
scripts/verify.sh
scripts/verify.sh full
python3 /Users/gaofeng/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .
```
