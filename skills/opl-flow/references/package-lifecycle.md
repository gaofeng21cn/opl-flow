# Package Lifecycle

Keep these axes separate:

```text
Package     = stable OPL identity and capability intent
Publication = owner source/tag and published bytes
Carrier     = local install/update/remove and physical readback
Executor    = discovery and callability of installed capabilities
```

Framework v2 accepts a Package source on install and update. For a reviewed
Flow checkout containing the v2 `opl-package.json`, set `FLOW_SOURCE` to its
absolute directory and run the applicable action.

```bash
opl pack inspect "$FLOW_SOURCE" --json
opl pack install "$FLOW_SOURCE" --json
opl pack update opl-flow --source "$FLOW_SOURCE" --json
opl pack inspect opl-flow --json
codex plugin list --json
```

Install on a new node and use update for an existing Pack install. Verify the
Package ID, enabled state, version, and native plugin registration. The
configured release channel can also supply a compatible v2 artifact. Always use
the Framework v2 `opl pack` install, update, ensure, sync, and inspect commands.

Repository source verification does not install the Package or prove currentness.

Flow dependencies use stable identity and callability. Do not introduce a
second App list, central ABI/SemVer solver, shared release cohort, or lifecycle
owner. Transitional locks, payloads, receipts, and provenance are diagnostic
and recovery evidence, not the target composition model.

Legacy migration is source-aware. Back up and remove only a projection whose
lock/source/path proves the retired owner. A same-name directory with missing
or different provenance is a collision and must be preserved for review.

A version, tag, GHCR object, test, or task branch is not installed truth. Read
back the configured carrier and selected executor after every lifecycle action.
