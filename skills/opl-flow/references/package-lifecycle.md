# Package Lifecycle

Keep these axes separate:

```text
Package     = stable OPL identity and capability intent
Publication = owner source/tag and published bytes
Carrier     = local install/update/remove and physical readback
Executor    = discovery and callability of installed capabilities
```

Normal user actions use Framework:

```bash
opl packages install opl-flow --json
opl packages update opl-flow --json
opl packages repair --package-id opl-flow --json
opl packages status --package-id opl-flow --json
```

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
